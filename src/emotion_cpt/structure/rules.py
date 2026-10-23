"""结构计算规则入口（骨架）。

来源：CPT ``cpt/domain/`` 的 ``fractal`` / ``bi`` / ``zhongshu`` / ``contain`` /
``recursion`` / ``trend_type`` / ``signal`` / ``first_buy`` / ``levels`` 等模块。

**搬迁原则**：
- **逐字搬**（连 docstring 一起），不趁机重构 —— 重构会同时改行为与口径，风险不可控
- 搬迁后由 ``emotion_cpt.contracts.pricing`` 提供那 5 个常量（CPT 现在是它们的真源）
- 搬迁后 CPT 的 ``cpt/domain/`` 变成 **re-export**（保留向后兼容），而不是立刻删除
  ⇒ 上游零改动即可运行，采纳是渐进的
"""

from __future__ import annotations

from typing import Any, Protocol, Sequence

from .models import Bi, Fractal, TrendType, ZhongShu


class BarLike(Protocol):
    """K 线最小协议 —— 只要求 domain 真正用到的那几个属性。"""

    @property
    def index(self) -> int: ...

    @property
    def high(self) -> float: ...

    @property
    def low(self) -> float: ...


def compute_fractals(bars: Sequence[BarLike], *, min_bi_len: int | None = None) -> list[Fractal]:
    """计算分型。

    ⚠️ ``min_bi_len`` 是**构造参数**而不是全局常量 —— 上游曾因对比脚本用错口径
    （量到 99 笔 vs 生产 28 笔，差 3.5 倍）而返工。**门槛必须显式传入。**
    """
    raise NotImplementedError("P1 阶段填充：自 CPT cpt/domain/fractal.py 逐字搬迁")


def compute_bis(bars: Sequence[BarLike], *, min_bi_len: int | None = None) -> list[Bi]:
    """计算笔。"""
    raise NotImplementedError("P1 阶段填充：自 CPT cpt/domain/bi.py 逐字搬迁")


def compute_zhongshus(bars: Sequence[BarLike], *, min_bi_len: int | None = None) -> list[ZhongShu]:
    """计算中枢。"""
    raise NotImplementedError("P1 阶段填充：自 CPT cpt/domain/zhongshu.py 逐字搬迁")


def classify_trend(bis: Sequence[Bi], zhongshus: Sequence[ZhongShu]) -> list[TrendType]:
    """判定趋势类型。"""
    raise NotImplementedError("P1 阶段填充：自 CPT cpt/domain/trend_type.py 逐字搬迁")


__all__ = ("BarLike", "classify_trend", "compute_bis", "compute_fractals", "compute_zhongshus")
