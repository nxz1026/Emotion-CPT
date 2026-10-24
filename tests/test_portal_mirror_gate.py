"""★ portal 镜像门禁的**自证**：注入漂移 ⇒ 必须报红。

纪律来源：上游 R45 —— *「自制的验证工具第一版基本都错」*。
**跑全绿不够，必须注入假数据确认它还能报。**

这个门禁第一版有个**真问题**：它拿 portal 镜像与真相源做**逐字**比对
⇒ 真相源里的 ``# owner:`` 注释（归属声明）让 16 个 unit **全部**报差异，
而它们的实际内容**一模一样** ⇒ **假警报**。
⇒ 第二版加了**归一化**（比对前去掉 owner 注释行）。

⇒ 这里的用例把两件事都钉住：
1. **真漂移**（内容不同）⇒ 必须报
2. **只有 owner 注释不同** ⇒ **不得**报（否则门禁天天假红 ⇒ 被人忽略）
"""

from __future__ import annotations

import pathlib

from emotion_cpt.cli import check_portal_mirror as cpm

#: 一份最小的 unit 内容
UNIT = """[Unit]
Description={desc}
After=network.target

[Service]
ExecStart=/usr/bin/python3 -m something
"""


def _write(d: pathlib.Path, name: str, body: str) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")


def test_content_drift_is_reported(tmp_path: pathlib.Path) -> None:
    """★ 内容不同 ⇒ 必须报（真漂移）。"""
    portal = tmp_path / "portal"
    truth = tmp_path / "truth"
    _write(portal, "a.service", UNIT.format(desc="ORIGINAL"))
    _write(truth, "a.service", UNIT.format(desc="CHANGED"))

    issues, _notes = cpm.compare(
        cpm._units(portal), cpm._units(truth), None
    )
    assert issues, "内容漂移必须报出来"
    assert "a.service" in issues[0]


def test_owner_comment_only_difference_is_not_reported(tmp_path: pathlib.Path) -> None:
    """★ **只有 owner 注释不同** ⇒ 不得报（否则门禁天天假红）。

    第一版就是栽在这里：真相源加了 ``# owner:`` 归属声明后，
    16 个 unit 全部报差异，而内容**完全一样**。
    """
    portal = tmp_path / "portal"
    truth = tmp_path / "truth"
    _write(portal, "a.service", UNIT.format(desc="SAME"))
    _write(truth, "a.service", "# owner: cpt\n" + UNIT.format(desc="SAME"))

    issues, _notes = cpm.compare(
        cpm._units(portal), cpm._units(truth), None
    )
    assert not issues, f"只有 owner 注释不同不该报，却报了：{issues}"


def test_missing_unit_is_a_note_not_an_error(tmp_path: pathlib.Path) -> None:
    """镜像里缺 unit ⇒ **只提示**，不报红。

    理由：修它要跑 portal 的 ``sync.sh pull``（会写 portal 仓），
    而 owner 裁决 Q7=C「不动 portal 仓」⇒ **一个长期红的门禁等于没有门禁**。
    而镜像缺 unit 对 Emotion-CPT 自身没有风险（本仓的 unit 有
    ``check_unit_paths`` 真相源↔线上 守着）。
    """
    portal = tmp_path / "portal"
    truth = tmp_path / "truth"
    _write(truth, "a.service", "# owner: emotion-cpt\n" + UNIT.format(desc="X"))

    issues, notes = cpm.compare(cpm._units(portal), cpm._units(truth), None)
    assert not issues, f"缺失不该报红，却报了：{issues}"
    assert notes and "a.service" in notes[0]


def test_live_drift_is_reported(tmp_path: pathlib.Path) -> None:
    """线上与真相源不一致 ⇒ 也要报（三方对账的第三方）。"""
    portal = tmp_path / "portal"
    truth = tmp_path / "truth"
    live = tmp_path / "live"
    _write(portal, "a.service", UNIT.format(desc="SAME"))
    _write(truth, "a.service", UNIT.format(desc="SAME"))
    _write(live, "a.service", UNIT.format(desc="LIVE-DIFF"))

    issues, _notes = cpm.compare(
        cpm._units(portal), cpm._units(truth), cpm._units(live)
    )
    assert issues, "线上漂移必须报出来"
    assert "线上" in issues[0]
