"""52 张 ``public`` 表的归属 manifest。

**真值（2026-10-23 Oracle 实测）**：52 张表 = emotion-core 自有 37 + CPT 自有 14 + 反契约表 1。
其中 CPT 的 14 张含 **5 张迁移遗留的备份/隔离表**（R67 迁移的丢弃数据，共 21,961 行）。

这张 manifest 的作用是让「这张表归谁」变成**机器可读的事实**，而不是散落在
markdown 表格和口头约定里的知识 —— 后者会随时间漂移（上游已实测到 8/10/28/33/36/41 六个口径）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

OWNER_EMOTION: Final[str] = "emotion-core"
OWNER_CPT: Final[str] = "cpt"


@dataclass(frozen=True)
class TableSpec:
    """一张表的归属声明。

    :param name: 表名
    :param owner: 归属项目（谁负责这张表的定义与迁移）
    :param writer: 写入方
    :param readers: 读取方
    :param legacy: 是否为迁移遗留的备份/隔离表（**不参与**业务，只占空间）
    """

    name: str
    owner: str
    writer: str
    readers: tuple[str, ...]
    legacy: bool = False


# ── emotion-core 自有（37 张，与 data/schema.py 的 DDL 一一对应）────────────────
_EMOTION_TABLES: Final[tuple[str, ...]] = (
    "alert", "daily_bar", "data_revision", "derived_bar", "eval_result", "holding_decision",
    "hot_rank", "ingest_progress", "ladder_day", "limit_pool_em", "llm_call_log", "market_stat",
    "ops_quota_ledger", "ops_raw_manifest", "pipeline_state", "position", "promotion_day",
    "ref_dividend", "ref_limit_rule", "ref_limit_state", "ref_limit_state_run", "ref_rs",
    "ref_security_status", "ref_security_status_event", "ref_security_status_window",
    "review_report", "signal", "signal_outcome", "stock_basic", "strategy_signal",
    "theme_group", "theme_spot", "theme_tag", "trade_calendar", "trade_event", "trigger_log",
    "watchlist",
)

# ── CPT 自有（在用 9 张）──────────────────────────────────────────────────────
_CPT_ACTIVE_TABLES: Final[tuple[str, ...]] = (
    "cpt_dashboard_run", "cpt_factor_epoch", "cpt_llm_call", "cpt_recommendation",
    "cpt_run_metric", "cpt_signal_event", "cpt_structure_event", "cpt_track",
    "cpt_track_snapshot",
)

# ── CPT 自有 ────────────────────────────────────────────────────────────
# ⚠️ 原先这里还有 5 张**迁移遗留的备份/隔离表**（21,962 行）：
#   cpt_structure_event_{deduped,dropped}_20261019
#   cpt_structure_event_id_backup_{20261001,20261019}
#   cpt_structure_event_quarantine_20261020
# ⇒ 2026-10-24 按 owner 裁决（Q4）**删除**，已备份到
#   /home/ubuntu/backups/legacy-tables-20261024-*.{dump,sql,manifest.txt}
#
# ⇒ 后果之一：CPT 的 R67 回滚脚本
#   `scripts/migrations/rollback/2026-10-19_r67_symbol_in_id_rollback.sql`
#   依赖这些备份表 ⇒ **现在回滚会明确报错**（RAISE EXCEPTION
#   「缺少备份表 … 无法回滚」）。这是**故意**的：宁可回滚失败，
#   也不要静默回滚到「少了一截」的状态。

#: CPT 写、emotion 读
_CPT_WRITTEN: Final[tuple[str, ...]] = ("intraday_seal_snapshot",)

#: emotion 写、CPT 读（与 contracts.shared_tables.SHARED_TABLES 对齐）
_EMOTION_WRITTEN_SHARED: Final[tuple[str, ...]] = (
    "daily_bar", "derived_bar", "hot_rank", "ladder_day", "limit_pool_em",
    "strategy_signal", "trade_calendar",
)

TABLES: Final[tuple[TableSpec, ...]] = (
    *(
        TableSpec(
            name=name,
            owner=OWNER_EMOTION,
            writer=OWNER_EMOTION,
            readers=(OWNER_CPT,) if name in _EMOTION_WRITTEN_SHARED else (OWNER_EMOTION,),
        )
        for name in _EMOTION_TABLES
    ),
    *(
        TableSpec(
            name=name,
            owner=OWNER_CPT,
            writer=OWNER_CPT,
            readers=(OWNER_EMOTION,),
        )
        for name in _CPT_ACTIVE_TABLES
    ),
    *(
        TableSpec(name=name, owner=OWNER_CPT, writer=OWNER_CPT, readers=(OWNER_EMOTION,))
        for name in _CPT_WRITTEN
    ),
)


def table_of(name: str) -> TableSpec | None:
    """按表名查 manifest。查不到返回 ``None``（不抛 —— 调用方多半在扫全库）。"""
    for spec in TABLES:
        if spec.name == name:
            return spec
    return None


def tables_of(owner: str) -> tuple[TableSpec, ...]:
    """按归属方取全部表。"""
    return tuple(spec for spec in TABLES if spec.owner == owner)


__all__ = ("OWNER_CPT", "OWNER_EMOTION", "TABLES", "TableSpec", "table_of", "tables_of")
