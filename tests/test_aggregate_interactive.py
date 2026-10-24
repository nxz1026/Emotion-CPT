"""★ 聚合页的两条硬要求：**输入能生效** + **不能退化成空壳**。

## ① 输入能生效（owner 报过的 bug）

表单是 GET，但 ``action`` 曾经指向 ``/aggregate/stock/{当时那个代码}``
⇒ 浏览器导航到 ``.../stock/600519?code=你输的``
⇒ **后端走的是「路径参数」路由** ⇒ 查询参数被**忽略**
⇒ 页面永远显示 600519 ⇒ **「输进去没反应」**。

⇒ 断言：表单的 action 必须指向**列表页**（以 ``aggregate`` 结尾、**不含** ``/stock/``）。

## ② 不能退化成空壳（owner 报过的「信息量有点小」）

``fetch_cpt_snapshot`` 早就在取 CPT 的完整行情，但 payload 压根没用它
⇒ 页面连价格都没有。

⇒ 断言：payload 里必须带 **行情 / 结构级别树 / 引擎 / 数据质量** 四块
⇒ 少一块就红（防止以后又被"精简"掉）。
"""

from __future__ import annotations

import re

import pytest

from emotion_cpt.web import app
from emotion_cpt.web.aggregate import server


@pytest.fixture(scope="module")
def payload() -> dict:
    return server.build_stock_payload("600519")


# ─────────────────── ① 输入能生效 ───────────────────


def test_form_action_points_to_list_page(payload: dict) -> None:
    """★ action 必须指向列表页（靠 ?code= 传参）。"""
    html = app._aggregate_page("600519", payload, "/ecpt/").decode("utf-8")
    m = re.search(r'<form action="([^"]+)"', html)
    assert m, "页面里找不到表单"
    action = m.group(1)
    assert action.endswith("aggregate"), f"action 必须指向列表页，却是 {action!r}"
    assert "/stock/" not in action, (
        f"action 里带了 /stock/ ⇒ 浏览器会导航到**路径参数**那个代码，"
        f"你输的 code 被忽略（{action!r}）"
    )


def test_form_action_uses_mount_prefix(payload: dict) -> None:
    """action 必须带挂载前缀（/ecpt/）⇒ 否则在 /ecpt/ 下解析错。"""
    html = app._aggregate_page("600519", payload, "/ecpt/").decode("utf-8")
    action = re.search(r'<form action="([^"]+)"', html).group(1)
    assert action.startswith("/ecpt/"), action


def test_code_query_param_is_honoured_by_backend() -> None:
    """★ 后端**本来就支持** ``?code=`` ⇒ 表单只要走这条路就行。

    （这条是回归守卫：万一有人把 ``/aggregate`` 路由的 query 读取删了，
    表单就会静默地永远显示默认代码。）
    """
    from emotion_cpt.web.aggregate.server import build_stock_payload

    p = build_stock_payload("000001")
    assert p.get("code") == "000001", f"后端忽略了 code：{p.get('code')}"


# ─────────────────── ② 不能退化成空壳 ───────────────────


def test_payload_carries_quote(payload: dict) -> None:
    """★ 行情必须在 payload 里（此前压根没取）。"""
    cpt = payload["panels"]["cpt"]
    assert "quote" in cpt, "cpt 面板没有 quote"
    assert cpt["quote"].get("available") is True
    for key in ("close", "high", "low", "bar_count", "last_bar_date"):
        assert key in cpt["quote"], f"quote 缺 {key}"


def test_payload_carries_levels_tree(payload: dict) -> None:
    """★ CPT 的结构级别树（确定性缠论最硬的部分）必须在。"""
    cpt = payload["panels"]["cpt"]
    assert "levels_tree" in cpt, "cpt 面板没有 levels_tree"
    assert cpt["levels_tree"].get("available") is True
    assert cpt["levels_tree"]["levels"], "结构级别树是空的"


def test_payload_carries_engine_and_quality(payload: dict) -> None:
    """引擎状态与数据质量 —— 结论建立在什么数据上，必须看得见。"""
    cpt = payload["panels"]["cpt"]
    assert "engine" in cpt
    assert "quality" in cpt


def test_page_renders_new_sections(payload: dict) -> None:
    """★ 页面上必须有「行情 / 结构级别树 / 数据可信度」三个区块。"""
    html = app._aggregate_page("600519", payload, "/ecpt/").decode("utf-8")
    for heading in ("行情", "结构级别树", "数据可信度"):
        assert heading in html, f"页面缺「{heading}」区块"
    assert html.count("<table") >= 2, "结构级别树应该是一张表"


def test_stop_loss_shows_its_explanation(payload: dict) -> None:
    """★ 止损没有价位时，必须显示**原因**（此前只有 ``None (pct_fallback)``）。

    emotion-core 给的是「无当日行情（未上市 / 停牌超窗 / 尚未回补）→ 不给价位（F6 不猜）」
    ⇒ 只显示 ``None`` 看着像坏了。
    """
    stop = payload["panels"]["emotion"].get("stop") or {}
    if stop.get("price") is None and stop.get("detail"):
        html = app._aggregate_page("600519", payload, "/ecpt/").decode("utf-8")
        assert "pct_fallback" in html
        assert str(stop["detail"])[:12] in html, "止损的解释文字没显示"
