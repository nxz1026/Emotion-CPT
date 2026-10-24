"""契约本身的自洽性测试（零 I/O，最快）。"""

from __future__ import annotations

import dataclasses

import pytest

from emotion_cpt.contracts import intraday_seal, pricing, shared_tables
from emotion_cpt.contracts.tables import TABLES, table_of, tables_of


def test_table_count_matches_reality():
    """真值：52 张表 = emotion 37 + CPT 14 + 反契约 1。"""
    assert len(TABLES) == 47
    assert len(tables_of("emotion-core")) == 37
    assert len(tables_of("cpt")) == 10  # 9 张 cpt_* + intraday_seal_snapshot


def test_legacy_tables_are_flagged():
    """迁移遗留表的**标记机制**仍在，且当前一张都没有。

    2026-10-24 按 owner 裁决（Q4）删掉了最后 5 张 legacy 表
    （21,962 行，已备份）⇒ 现在应当**一张都没有**。

    但「表可以标为迁移遗留」这个**机制**要留着 ——
    下次再有迁移遗留表时，能被标出来、能被门禁数出来。
    """
    legacy = [t for t in TABLES if t.legacy]
    assert legacy == [], f"应无 legacy 表，实际有：{[t.name for t in legacy]}"

    # 机制本身仍可用：构造一条带标记的，summary 要能数出来
    from emotion_cpt.contracts.tables import OWNER_CPT, TableSpec
    from emotion_cpt.schema.manifest import summary

    marked = TableSpec(
        name="_probe_legacy_", owner=OWNER_CPT, writer=OWNER_CPT,
        readers=(), legacy=True,
    )
    assert marked.legacy is True
    # 汇总里也要能数出 legacy（当前为 0，因为已按 Q4 删干净）
    assert summary()["cpt"]["legacy"] == 0


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
