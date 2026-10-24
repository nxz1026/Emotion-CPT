"""manifest 与真实项目结构的一致性。"""

from __future__ import annotations

from emotion_cpt.contracts.tables import OWNER_CPT, OWNER_EMOTION, TABLES, tables_of


def test_emotion_tables_are_37():
    assert len(tables_of(OWNER_EMOTION)) == 37


def test_cpt_side_has_9_cpt_tables_plus_reverse():
    cpt = tables_of(OWNER_CPT)
    named = [t for t in cpt if t.name.startswith("cpt_")]
    reverse = [t for t in cpt if t.name == "intraday_seal_snapshot"]
    assert len(named) == 9
    assert len(reverse) == 1


def test_shared_tables_have_two_readers():
    """7 张共享表：emotion 写、CPT 读。"""
    shared = [t for t in TABLES if t.name in {
        "daily_bar", "derived_bar", "hot_rank", "ladder_day",
        "limit_pool_em", "strategy_signal", "trade_calendar",
    }]
    assert len(shared) == 7
    for spec in shared:
        assert spec.writer == OWNER_EMOTION
        assert OWNER_CPT in spec.readers
