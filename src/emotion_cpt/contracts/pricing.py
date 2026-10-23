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

#: 价格取整位数。
#:
#: A 股价格最小变动单位是 **0.01 元** ⇒ 结构位取整到**分**即可；
#: 3 位小数（0.001 元）是**伪精度** —— 盘口根本没有这个刻度。
#:
#: ⚠️ 2026-10-23 口径收敛：此前 CPT 用 2 位、emotion-core 用 3 位，
#: 实测同一批 overlays 下 **36 个价有 29 个不一致**（最大差 0.005 元）⇒
#: 同一只票在两个系统印出不同的买/卖点价。现统一为 2 位。
PRICE_ROUND_DIGITS: Final[int] = 2

#: 取最近 N 笔
BI_LOOKBACK: Final[int] = 3

#: 取最近 N 个中枢
ZHONGSHU_LOOKBACK: Final[int] = 2

__all__ = (
    "BI_LOOKBACK",
    "PRICE_ROUND_DIGITS",
    "BUY_BUFFER",
    "SELL_BUFFER",
    "STOP_LOSS_RATIO",
    "ZHONGSHU_LOOKBACK",
)
