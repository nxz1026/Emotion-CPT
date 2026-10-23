"""价格与结构位计算的**唯一**常量定义处。

⚠️ 这些值原先被 emotion-core 手抄了一份（``algorithms/levels.py``），
手抄副本的注释里连行号引用都已经差了一行 —— 典型的"同一事实的两份拷贝"。
本模块是它们的唯一真源；上游采纳后，漂移通道物理关闭。

变更本模块的任何值 = **破坏性变更**：需要版本号 + 弃用期。
"""

from __future__ import annotations

from typing import Final

#: BUY 参考位的缓冲：在算出的 raw 价上再上调 2%
BUY_BUFFER: Final[float] = 1.02

#: SELL 参考位的缓冲：在算出的 raw 价上再下调 3%
SELL_BUFFER: Final[float] = 0.97

#: 止损相对 BUY 参考位的比例
STOP_LOSS_RATIO: Final[float] = 0.95

#: 取最近 N 笔
BI_LOOKBACK: Final[int] = 3

#: 取最近 N 个中枢
ZHONGSHU_LOOKBACK: Final[int] = 2

__all__ = (
    "BI_LOOKBACK",
    "BUY_BUFFER",
    "SELL_BUFFER",
    "STOP_LOSS_RATIO",
    "ZHONGSHU_LOOKBACK",
)
