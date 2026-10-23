"""``public.intraday_seal_snapshot`` 的 9 列唯一定义。

方向：**CPT 写 → emotion-core 读**（与 7 张共享表方向相反，故单独成文）。

这张表的漂移代价特别高：列名与**单位**都可能悄悄不一致 ——
``bid1_lots`` 是「手」不是「股」（读方阈值按股时要 ×100），
``distance_pct`` 是**百分数**不是小数。所以单位与语义写进契约本体，不只写注释。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

INTRADAY_SEAL_TABLE: Final[str] = "intraday_seal_snapshot"


@dataclass(frozen=True)
class Column:
    """一列的契约声明。

    :param name: 列名
    :param dtype: Postgres 类型
    :param nullable: 是否可空
    :param unit: 单位（无则 None）。**单位不一致是最贵的漂移**，必须显式。
    :param semantics: 语义说明。判据归属（「谁判的」）也要写在这里。
    """

    name: str
    dtype: str
    nullable: bool
    unit: str | None = None
    semantics: str = ""


INTRADAY_SEAL_COLUMNS: Final[tuple[Column, ...]] = (
    Column("at", "timestamptz", False, semantics="本轮采集时刻；UTC 存储、UTC 输出"),
    Column("code", "text", False, semantics="6 位纯代码，如 '600293'"),
    Column("sealed", "boolean", False, semantics="这一轮是否封在板上"),
    Column(
        "bid1_lots",
        "double precision",
        True,
        unit="手（1 手 = 100 股）",
        semantics="买一挂单量；读方阈值用股时必须 ×100",
    ),
    Column(
        "limit_price",
        "double precision",
        True,
        semantics="本轮用的涨停价（CPT 的 Decimal 取整口径，读方自算会差一分钱）",
    ),
    Column("price", "double precision", True, semantics="本轮现价"),
    Column("prev_close", "double precision", True, semantics="昨收"),
    Column(
        "distance_pct",
        "double precision",
        True,
        unit="百分数（非小数）",
        semantics="(limit_price - price) / limit_price * 100；0.0 = 封在板上，负数 = 已超板",
    ),
    Column(
        "is_st",
        "boolean",
        True,
        semantics="ST 判定结果；NULL = 没判。判据归 CPT（ADR 0003 §E2「判据只许一处」）",
    ),
)

__all__ = ("INTRADAY_SEAL_COLUMNS", "INTRADAY_SEAL_TABLE", "Column")
