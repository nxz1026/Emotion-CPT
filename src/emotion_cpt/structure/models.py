"""结构领域模型（骨架）。

来源：CPT ``cpt/domain/models.py``（293 行）—— ``Fractal`` / ``Bi`` / ``ZhongShu`` /
``TrendType`` / ``DivergenceStatus`` / ``Signal`` / ``StructureEvent`` 等。

**契约**（搬迁后必须保持）：
- 纯 dataclass，**无可变默认值**
- 不含任何 I/O、不含时间戳生成（时间由调用方注入）
- 字段名是**跨仓契约**的一部分：emotion-core 的 overlays 消费 CPT 的
  ``fractals`` / ``bis`` / ``zhongshus`` / ``trend_types`` 四个数组，字段名改 = 静默破契约
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Fractal:
    """分型。"""

    index: int
    kind: str          # "top" | "bottom"
    high: float
    low: float
    bar_index: int = -1


@dataclass(frozen=True)
class Bi:
    """笔。"""

    index: int
    direction: int      # -1 向下 / +1 向上
    high: float
    low: float
    start_index: int = -1
    end_index: int = -1


@dataclass(frozen=True)
class ZhongShu:
    """中枢。"""

    index: int
    high: float
    low: float
    start_index: int = -1
    end_index: int = -1


@dataclass(frozen=True)
class TrendType:
    """趋势类型。"""

    kind: str
    bi_count: int = 0
    zhongshu_count: int = 0


def to_overlay_payload(
    fractals: list[Fractal],
    bis: list[Bi],
    zhongshus: list[ZhongShu],
    trend_types: list[TrendType],
) -> dict[str, list[dict[str, Any]]]:
    """产出 CPT overlays 的四数组结构。

    ⚠️ 这四个数组名（``fractals`` / ``bis`` / ``zhongshus`` / ``trend_types``）
    是 **emotion-core 的消费契约**（``cpt_client.snapshot_overlays()`` 逐字取它们），
    改任何一个都会让 emotion-core 侧静默降级。
    """
    return {
        "fractals": [f.__dict__ for f in fractals],
        "bis": [b.__dict__ for b in bis],
        "zhongshus": [z.__dict__ for z in zhongshus],
        "trend_types": [t.__dict__ for t in trend_types],
    }


__all__ = ("Bi", "Fractal", "TrendType", "ZhongShu", "to_overlay_payload")
