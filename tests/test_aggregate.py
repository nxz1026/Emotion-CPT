"""聚合页的冲突检测（纯逻辑，不发请求）。"""

from __future__ import annotations

from emotion_cpt.web.aggregate.server import detect_conflicts


def test_buy_conflict_is_reported():
    conflicts = detect_conflicts({"action": "buy", "available": True}, {"buy_window": "NONE"})
    assert conflicts and conflicts[0]["kind"] == "buy_conflict"


def test_no_conflict_when_aligned():
    conflicts = detect_conflicts({"action": "buy", "available": True}, {"buy_window": "OPEN"})
    assert conflicts == []


def test_unknown_vocabulary_is_flagged():
    """词表漂移必须被报出来（契约变了但上游没跟）。"""
    conflicts = detect_conflicts({"action": "strong_buy", "available": True}, {"buy_window": "OPEN"})
    assert any(c["kind"] == "vocabulary" for c in conflicts)
