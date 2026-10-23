"""契约本身的自洽性测试（零 I/O，最快）。"""

from __future__ import annotations

import dataclasses

import pytest

from emotion_cpt.contracts import intraday_seal, pricing, shared_tables
from emotion_cpt.contracts.tables import TABLES, table_of, tables_of


def test_table_count_matches_reality():
    """真值：52 张表 = emotion 37 + CPT 14 + 反契约 1。"""
    assert len(TABLES) == 52
    assert len(tables_of("emotion-core")) == 37
    assert len(tables_of("cpt")) == 15  # 14 张 cpt_* + intraday_seal_snapshot


def test_legacy_tables_are_flagged():
    legacy = [t for t in TABLES if t.legacy]
    assert len(legacy) == 5
    assert all(t.name.startswith("cpt_structure_event_") for t in legacy)


def test_no_duplicate_table_names():
    names = [t.name for t in TABLES]
    assert len(names) == len(set(names))


def test_intraday_seal_has_nine_columns():
    assert len(intraday_seal.INTRADAY_SEAL_COLUMNS) == 9
    assert [c.name for c in intraday_seal.INTRADAY_SEAL_COLUMNS] == [
        "at", "code", "sealed", "bid1_lots", "limit_price",
        "price", "prev_close", "distance_pct", "is_st",
    ]


def test_unit_traps_are_recorded():
    """单位陷阱必须写在契约里（手 vs 股、百分数 vs 小数）。"""
    by_name = {c.name: c for c in intraday_seal.INTRADAY_SEAL_COLUMNS}
    assert by_name["bid1_lots"].unit is not None and "手" in by_name["bid1_lots"].unit
    assert by_name["distance_pct"].unit is not None
    assert "百分数" in by_name["distance_pct"].unit


def test_price_constants_values():
    assert pricing.BUY_BUFFER == 1.02
    assert pricing.SELL_BUFFER == 0.97
    assert pricing.STOP_LOSS_RATIO == 0.95
    assert pricing.BI_LOOKBACK == 3
    assert pricing.ZHONGSHU_LOOKBACK == 2


def test_shared_tables_direction():
    assert len(shared_tables.SHARED_TABLES) == 7
    assert all(t.writer == "emotion-core" for t in shared_tables.SHARED_TABLES)
    assert len(shared_tables.REVERSE_TABLES) == 1
    assert shared_tables.REVERSE_TABLES[0].writer == "cpt"


def test_contracts_are_immutable():
    """契约不可就地改写 —— 否则门禁的指纹就失去意义。"""
    for spec in TABLES:
        assert dataclasses.is_dataclass(spec)
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.name = "hacked"  # type: ignore[misc]


def test_table_of_unknown_returns_none():
    assert table_of("no_such_table") is None
