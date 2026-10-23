"""快照流水线（骨架）。

流水线形态::

    bars ──▶ structure.compute_fractals/bi/zhongshus ──▶ trend ──▶ signal
                                        │
                                        ▼
                          overlays（fractals/bis/zhongshus/trend_types）
                                        │
                                        ▼
                              structure levels（中枢/笔 → 买卖参考位）
                                        │
                                        ▼
                            snapshot payload（CPT overlay 形状 + emotion 判据）

**价格域陷阱（必须保留在实现里）**：
CPT 的 ``overlays`` 在**后复权（adj）域**，``daily_bar.close`` 在**不复权（raw）域**。
``ratio = adj ÷ raw`` 逐股逐日不同，**判不出就不许拿 adj 域的数当 raw 用**
（会把 1258 当成 8886）。ratio 无效时走百分比兜底并在明细里写明原因。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass(frozen=True)
class SnapshotResult:
    """一次快照的结果。"""

    code: str
    trade_date: str
    overlays: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    levels: dict[str, Any] = field(default_factory=dict)
    signal: dict[str, Any] | None = None
    price_ratio: float | None = None
    degraded: bool = False
    degraded_reason: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def compute_snapshot(
    code: str,
    trade_date: str,
    bars: Sequence[Any],
    *,
    price_ratio: float | None = None,
    min_bi_len: int | None = None,
) -> SnapshotResult:
    """计算一次快照。P1 阶段填充实现。"""
    raise NotImplementedError("P1 阶段填充：编排 structure.rules + levels 计算")


__all__ = ("SnapshotResult", "compute_snapshot")
