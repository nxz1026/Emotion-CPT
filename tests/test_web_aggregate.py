"""聚合页的**纯逻辑**测试（不发请求）。"""

from __future__ import annotations

from emotion_cpt.web.aggregate.server import _conflicts, _direction, _verdicts


def test_direction_normalisation():
    assert _direction({"buy": "看多"}, "buy") == "看多"
    assert _direction({"sell": "看空"}, "sell") == "看空"
    assert _direction({"watch": "观望"}, "watch") == "观望"
    assert _direction({"buy": "看多"}, "nonsense") == "未知"
    assert _direction({"buy": "看多"}, None) == "未知"


def test_buy_conflict_detected():
    """CPT 说买、emotion 持仓说持有 ⇒ 必须报出来。"""
    conflicts = _conflicts("buy", "HOLD", [], "cpt_structure")
    assert any(c["kind"] == "buy_conflict" for c in conflicts)


def test_no_conflict_when_aligned():
    conflicts = _conflicts("buy", "ADD", [], "cpt_structure")
    assert not any(c["kind"] == "buy_conflict" for c in conflicts)


def test_strategy_disagree_detected():
    conflicts = _conflicts("buy", "ADD", [{"action": "PASS"}], "cpt_structure")
    assert any(c["kind"] == "strategy_disagree" for c in conflicts)


def test_levels_fallback_flagged():
    """结构位走兜底 ⇒ 要标出来（是数据不完整，不是口径冲突）。"""
    conflicts = _conflicts("watch", "HOLD", [], "pct_fallback")
    assert any(c["kind"] == "levels_degraded" for c in conflicts)


def test_verdicts_rows():
    rows = _verdicts("buy", "HOLD", [{"action": "WATCH"}])
    assert len(rows) == 3
    assert rows[0]["source"].startswith("CPT")
    assert rows[0]["cls"] == "up"
    assert rows[1]["cls"] == "flat"
