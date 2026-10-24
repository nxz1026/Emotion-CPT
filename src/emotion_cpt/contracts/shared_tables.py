"""emotion-core 写、CPT 读的 7 张共享表。

方向：**emotion-core → CPT**（与 :mod:`emotion_cpt.contracts.intraday_seal` 相反）。

新鲜度判据：**收盘时刻（北京时间 15:00）已过的最近一个交易日**。
判错会在每个假期误报一次，一周之内这检查就没人看了 —— 所以判据本身也是契约。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class SharedTable:
    """一张共享表。

    :param name: 表名
    :param date_column: 判定新鲜度用的日期列
    :param writer: 写入方
    :param source: 数据来源（人类可读）
    """

    name: str
    date_column: str
    writer: str
    source: str


SHARED_TABLES: Final[tuple[SharedTable, ...]] = (
    SharedTable(
        "daily_bar",
        "date",
        "emotion-core",
        "东财 push2delay 全市场快照；502 回退新浪；pytdx 回填",
    ),
    SharedTable("derived_bar", "date", "emotion-core", "无外部源，纯 SQL 派生自 daily_bar"),
    SharedTable("hot_rank", "date", "emotion-core", "东财人气榜 top100"),
    SharedTable(
        "ladder_day",
        "date",
        "emotion-core",
        "无外部源，派生自 derived_bar / limit_pool_em",
    ),
    SharedTable("limit_pool_em", "date", "emotion-core", "akshare 涨停/炸板/跌停池"),
    SharedTable("strategy_signal", "trade_date", "emotion-core", "LLM 策略观察（15 个 YAML 策略）"),
    SharedTable(
        "trade_calendar",
        "date",
        "emotion-core",
        "akshare 新浪交易日历，刻意独立于库内行情数据",
    ),
)

#: 反向契约表（CPT 写 → emotion-core 读）。方向不同、新鲜度判据不同（日频 vs 盘中每 2 分钟），
#: 故**不并进**上面的清单 —— 混在一起判会让「盘中轮次」被按日频标准误判成陈旧。
REVERSE_TABLES: Final[tuple[SharedTable, ...]] = (
    SharedTable(
        "intraday_seal_snapshot",
        "at",
        "cpt",
        "CPT 盘中采集守护写入的每轮封板结论（只存结论，不存原始五档）",
    ),
)

__all__ = ("REVERSE_TABLES", "SHARED_TABLES", "SharedTable")
