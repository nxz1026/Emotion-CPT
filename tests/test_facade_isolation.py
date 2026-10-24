"""★ 隔离性自证：Emotion-CPT 是**独立故障域**。

要证明的是一句话：**上游（emotion-core / CPT）挂了，Emotion-CPT 照常工作。**

这个项目从 P4 就定了「**不合并进程** —— 保持 8010 / 8098 / 8091 三个故障域」，
但「保持三个故障域」说的是**上游之间**不合并；**Emotion-CPT 自己**是否也独立，
一直没有**可执行的证据** —— 只是一句设计声明。

⇒ 本文件把那句话变成**会失败的断言**，三条证据：

1. **进程层** —— 门面的 unit 不依赖 postgresql、不用上游 venv
   （静态断言真相源里的 unit 文件）
2. **数据层** —— 上游**全部**不可达时，``/api/health`` 仍 200，
   且逐个报出「不可达 + 原因」，**而不是崩**
3. **页面层** —— 上游**全部**不可达时，聚合页仍 200（**降级展示**，不是 500）

⚠️ 第 2/3 条必须**真的把上游打死**才算数。
这里用**死端口**（127.0.0.1:1 连不上）而不是停生产服务 ——
既是同样的效果，又不碰生产。
"""

from __future__ import annotations

import json
import pathlib
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from emotion_cpt.web.aggregate import clients
from emotion_cpt.web.app import FacadeHandler

#: 真相源里的门面 unit（CI 上没有 /etc/systemd/system ⇒ 用仓内真相源）
UNIT = (
    pathlib.Path(__file__).resolve().parents[1]
    / "src/emotion_cpt/deploy/systemd/emotion-cpt-web.service"
)

#: 死端口（连不上）—— 比停生产服务安全，效果一样
DEAD_CPT = "http://127.0.0.1:1"
DEAD_EMOTION = "http://127.0.0.1:2"


@pytest.fixture
def dead_upstreams(monkeypatch: pytest.MonkeyPatch) -> None:
    """把两个上游都指向死端口。"""
    monkeypatch.setattr(clients, "CPT_BASE", DEAD_CPT)
    monkeypatch.setattr(clients, "EMOTION_BASE", DEAD_EMOTION)


@pytest.fixture
def facade():
    """起一个**临时**门面实例（随机端口，不碰生产的 8092）。"""
    server = ThreadingHTTPServer(("127.0.0.1", 0), FacadeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def _get(url: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
            return int(resp.status), resp.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read()


# ─────────────────── ① 进程层 ───────────────────


def test_facade_unit_does_not_depend_on_database() -> None:
    """门面的 unit **不依赖数据库** ⇒ 上游/DB 挂了它照常起。"""
    text = UNIT.read_text(encoding="utf-8")
    assert "postgresql" not in text, (
        "门面的 unit 依赖了 postgresql ⇒ DB 挂了门面起不来，"
        "「独立故障域」就不成立了"
    )


def test_facade_unit_does_not_use_upstream_venv() -> None:
    """门面用**系统 python3**，不借上游的 venv ⇒ 上游 venv 坏了不影响它。"""
    text = UNIT.read_text(encoding="utf-8")
    assert "/usr/bin/python3" in text, text
    for upstream_venv in ("Chan_Pattern_Trader/.venv", "emotion-core/.venv"):
        assert upstream_venv not in text, f"门面借了上游的 venv：{upstream_venv}"


def test_facade_unit_has_its_own_working_directory() -> None:
    """工作目录是 Emotion-CPT 自己的仓 ⇒ 不受上游仓状态影响。"""
    text = UNIT.read_text(encoding="utf-8")
    assert "WorkingDirectory=/home/ubuntu/DSH/Emotion-CPT" in text, text


# ─────────────────── ② 数据层 ───────────────────


def test_health_still_200_when_all_upstreams_dead(facade: str, dead_upstreams) -> None:
    """★ 上游全部不可达 ⇒ ``/api/health`` 仍 200。"""
    status, body = _get(f"{facade}/api/health")
    assert status == 200, f"上游全挂时 health 应仍可用，却返回 {status}：{body[:300]!r}"


def test_health_reports_each_upstream_as_unreachable(
    facade: str, dead_upstreams
) -> None:
    """逐个报出「不可达 + 原因」——**不是崩,是可见的降级**。

    ⚠️ 只断言 ``cpt`` 与 ``emotion_core`` —— 这两个是本测试**打死**的。
    ``lab`` 走的是 ``app.py`` 里硬编码的 URL（不走 clients 模块），
    它在本机真的在跑 ⇒ 报 ``ok: True`` 是**正确**行为，不该被这条断言管。
    """
    status, body = _get(f"{facade}/api/health")
    assert status == 200
    payload = json.loads(body)
    assert payload["ok"] is True
    for key in ("cpt", "emotion_core"):
        entry = payload[key]
        assert entry["ok"] is False, f"{key} 应报不可达，却报 {entry}"
        assert entry["error"], f"{key} 应带错误原因，却是 {entry}"
    # lab 至少要被**报出来**（值随环境而定，不在这条断言范围内）
    assert "lab" in payload


def test_health_self_is_always_ok(facade: str, dead_upstreams) -> None:
    """**自己**始终是好的 —— 门面自己的可用性不依赖上游。"""
    _status, body = _get(f"{facade}/api/health")
    payload = json.loads(body)
    assert payload["self"] == "emotion-cpt-facade"
    assert payload["ok"] is True


# ─────────────────── ③ 页面层 ───────────────────


def test_portal_page_still_renders_when_upstreams_dead(
    facade: str, dead_upstreams
) -> None:
    """门户页不依赖上游 ⇒ 上游全挂也能开。"""
    status, body = _get(f"{facade}/")
    assert status == 200, f"门户页应仍可开，却返回 {status}"
    assert b"<html" in body.lower()


def test_aggregate_page_degrades_instead_of_crashing(facade: str, dead_upstreams) -> None:
    """★ 聚合页在上游全挂时**降级展示**（200），**不是 500**。

    这条最关键：聚合页是「同票并排」，两边都拿不到时
    必须是「两边都显示不可达」，而不是整个页面报错。
    """
    status, body = _get(f"{facade}/aggregate/stock/000001")
    assert status == 200, f"上游全挂时聚合页应降级为 200，却返回 {status}：{body[:300]!r}"
    assert b"<html" in body.lower()


def test_aggregate_api_reports_errors_per_source(facade: str, dead_upstreams) -> None:
    """聚合页的 JSON 里要**逐源**带错误 ⇒ 页面能分别标「不可达」。"""
    status, body = _get(f"{facade}/api/aggregate/stock/000001")
    assert status == 200
    payload = json.loads(body)
    assert payload["ok"] is True
    # 两个上游的错都要在 payload 里，不是静默的空
    text = json.dumps(payload, ensure_ascii=False)
    assert "127.0.0.1:1" in text or "refused" in text.lower() or "error" in text.lower()
