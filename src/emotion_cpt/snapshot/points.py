"""结构位 → 买卖参考位（**唯一实现**）。

## 为什么有这个模块

同一份算式**曾被两边各写一份**：

- CPT ``cpt/application/track_points.py`` —— 2 位小数，附 ``condition``/``rationale`` 文案
- emotion-core ``algorithms/levels.py`` —— 3 位小数，附 ``Levels`` 载荷 + 百分比兜底

两份公式相同（中枢下沿 / 向下笔低点取 min、÷ratio×``BUY_BUFFER``；
中枢上沿 / 向上笔高点取 max、÷ratio×``SELL_BUFFER``），
但**取整位数不同** ⇒ 实测同一批 overlays 下 36 个价有 **29 个不一致**（最大差 0.005 元），
**同一只票在两个系统印出不同的买/卖点价**。

2026-10-23 统一到本模块：公式、常量、取整**单一真源**。

## 价格域（最容易出错的地方）

CPT 的 ``overlays`` 在**后复权（adj）域**，``daily_bar.close`` 在**不复权（raw）域**。
``price_ratio = adj ÷ raw`` 由 CPT 现算（逐股逐日不同）。
**ratio 无效时绝不拿 adj 域的数当 raw 用**（会把 1258 当成 8886）——
返回 ``None``，由调用方走自己的兜底策略。

## 取整

统一到 :data:`emotion_cpt.contracts.pricing.PRICE_ROUND_DIGITS`（= 2 位）。
A 股最小变动单位是 0.01 元，3 位小数是伪精度。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from emotion_cpt.contracts.pricing import (
    BI_LOOKBACK,
    BUY_BUFFER,
    PRICE_ROUND_DIGITS,
    SELL_BUFFER,
    ZHONGSHU_LOOKBACK,
)

__all__ = ("Pick", "confirmed_point", "structure_pick", "structure_picks")

#: 笔的方向
DIR_DOWN: Final[int] = -1
DIR_UP: Final[int] = 1


@dataclass(frozen=True)
class Pick:
    """一个结构位的计算结果。

    :param price_level: raw 域价格（已按 ``PRICE_ROUND_DIGITS`` 取整）；不可用时 ``None``
    :param label: 命中的候选标签（**adj 域**，如 ``中枢下沿 1308.88``）
    :param adjusted: 命中的 adj 域价
    :param n_candidates: 候选个数（0 = 没有结构数据）
    :param reason: 没有候选时的原因文案
    """

    price_level: float | None = None
    label: str | None = None
    adjusted: float | None = None
    n_candidates: int = 0
    reason: str | None = None


def _num(value: Any) -> float | None:
    """可解析的**正**数 → float；None / NaN / 非数 / <=0 / bool → None。

    ``bool`` 显式排除（``True`` 会变成 1.0，是价格域里明显的脏数据）。
    口径比 CPT 原实现更严：价格 <= 0 在盘口里不存在，
    与其让 0 元价位流出去，不如当"没有结构数据"。
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f <= 0:  # NaN 或非正
        return None
    return f


def _field(obj: Any, name: str) -> Any:
    """取结构对象上的字段（dict 或 dataclass 都认）。"""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _to_raw(adjusted: float, price_ratio: float | None) -> float | None:
    """后复权 → raw。``price_ratio`` 不可用时返 None，不静默用错数。"""
    if price_ratio is None or price_ratio <= 0:
        return None
    return adjusted / price_ratio


def _candidates(overlays: dict[str, Any], side: str) -> list[tuple[str, float]]:
    """收集候选（标签, adj 域价）。

    - 买侧：最近 ``ZHONGSHU_LOOKBACK`` 个中枢的 ``low`` ∪ 最近 ``BI_LOOKBACK`` 笔中
      ``direction == -1`` 的 ``low``
    - 卖侧：最近 ``ZHONGSHU_LOOKBACK`` 个中枢的 ``high`` ∪ 最近 ``BI_LOOKBACK`` 笔中
      ``direction == +1`` 的 ``high``
    """
    if not isinstance(overlays, dict):
        return []
    zhongshus = overlays.get("zhongshus")
    bis = overlays.get("bis")
    if not isinstance(zhongshus, list) or not isinstance(bis, list):
        return []

    out: list[tuple[str, float]] = []
    if side == "buy":
        for zs in zhongshus[-ZHONGSHU_LOOKBACK:]:
            low = _num(_field(zs, "low"))
            if low is not None:
                out.append((f"中枢下沿 {low:.2f}", low))
        for bi in bis[-BI_LOOKBACK:]:
            if _field(bi, "direction") == DIR_DOWN:
                low = _num(_field(bi, "low"))
                if low is not None:
                    out.append((f"向下笔低点 {low:.2f}", low))
    else:
        for zs in zhongshus[-ZHONGSHU_LOOKBACK:]:
            high = _num(_field(zs, "high"))
            if high is not None:
                out.append((f"中枢上沿 {high:.2f}", high))
        for bi in bis[-BI_LOOKBACK:]:
            if _field(bi, "direction") == DIR_UP:
                high = _num(_field(bi, "high"))
                if high is not None:
                    out.append((f"向上笔高点 {high:.2f}", high))
    return out


def structure_pick(
    overlays: dict[str, Any] | None, price_ratio: float | None, side: str
) -> Pick:
    """算单侧结构位（``side`` ∈ ``{"buy", "sell"}``）。

    :param overlays: CPT snapshot 的 ``overlays``（adj 域）
    :param price_ratio: ``adj ÷ raw``；``None`` 或非正 ⇒ 无结构位
    """
    if side not in ("buy", "sell"):
        raise ValueError(f"side 只能是 'buy' / 'sell'，收到 {side!r}")

    if price_ratio is None or price_ratio <= 0:
        return Pick(reason="price_ratio 无效或未取到 → 结构位不可换算（不用 adj 域充数）")

    candidates = _candidates(overlays or {}, side)
    if not candidates:
        return Pick(
            n_candidates=0,
            reason="overlays.bis / zhongshus 为空（可能是 degraded snapshot）",
        )

    if side == "buy":
        label, raw_adj = min(candidates, key=lambda x: x[1])   # 取最低（最保守）
        buffer = BUY_BUFFER
    else:
        label, raw_adj = max(candidates, key=lambda x: x[1])   # 取最高（最保守）
        buffer = SELL_BUFFER

    raw = _to_raw(raw_adj, price_ratio)
    if raw is None:
        return Pick(n_candidates=len(candidates), reason="price_ratio 无效 → 无法换算为 raw")

    return Pick(
        price_level=round(raw * buffer, PRICE_ROUND_DIGITS),
        label=label,
        adjusted=raw_adj,
        n_candidates=len(candidates),
    )


def structure_picks(
    overlays: dict[str, Any] | None, price_ratio: float | None
) -> tuple[float | None, float | None]:
    """算两点的 raw 域价格：``(买结构位, 卖结构位)``；不可用的一侧为 ``None``。"""
    buy = structure_pick(overlays, price_ratio, "buy")
    sell = structure_pick(overlays, price_ratio, "sell")
    return buy.price_level, sell.price_level


def confirmed_point(
    last_bi: Any, last_zs: Any, price_ratio: float | None, side: str
) -> dict[str, Any] | None:
    """确凿点 = **最新一笔**的低/高点 + 0 缓冲（与 reference 同源不同采）。

    仅在 ``signal.status == "confirmed"`` 且 ``action`` 匹配时被调。
    """
    if side not in ("buy", "sell"):
        return None
    obj = last_zs if last_zs is not None else last_bi
    if obj is None or price_ratio is None or price_ratio <= 0:
        return None
    adj = _num(_field(obj, "low" if side == "buy" else "high"))
    if adj is None:
        return None
    raw = _to_raw(adj, price_ratio)
    if raw is None:
        return None
    return {
        "price_level": round(raw, PRICE_ROUND_DIGITS),
        "condition": "信号已经走到确认这一步，且价格仍在区间内",
        "rationale": (
            f"取最新结构的{'下沿' if side == 'buy' else '上沿'} {adj:.2f}（adjusted）÷ {price_ratio:.4f}"
        ),
    }
