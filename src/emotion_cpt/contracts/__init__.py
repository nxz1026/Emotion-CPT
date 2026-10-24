"""跨项目契约 —— **唯一定义处**。

这里放的是「CPT 与 emotion-core 之间的约定」，不是业务逻辑。
任何一条约定都只允许在**本模块**里写死一次；上游若要遵守，通过 import 本包，
而不是各自手抄一份（手抄 = 漂移通道，且没有测试会红）。
"""

from __future__ import annotations

from .intraday_seal import INTRADAY_SEAL_COLUMNS, INTRADAY_SEAL_TABLE
from .pricing import BI_LOOKBACK, BUY_BUFFER, SELL_BUFFER, STOP_LOSS_RATIO, ZHONGSHU_LOOKBACK
from .shared_tables import REVERSE_TABLES, SHARED_TABLES
from .tables import TABLES, TableSpec, table_of, tables_of

__all__ = (
    "BI_LOOKBACK",
    "BUY_BUFFER",
    "INTRADAY_SEAL_COLUMNS",
    "INTRADAY_SEAL_TABLE",
    "REVERSE_TABLES",
    "SELL_BUFFER",
    "SHARED_TABLES",
    "STOP_LOSS_RATIO",
    "TABLES",
    "TableSpec",
    "ZHONGSHU_LOOKBACK",
    "table_of",
    "tables_of",
)
