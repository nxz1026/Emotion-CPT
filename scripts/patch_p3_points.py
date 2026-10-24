#!/usr/bin/env python3
"""P3 补丁：把「结构位 → 买卖参考位」的算式统一到 emotion_cpt.snapshot.points。

改动两处（各自保留自己的载荷/文案/兜底，只把**算式与常量**换成共享实现）：

1. CPT ``cpt/application/track_points.py``
   - 常量 → ``emotion_cpt.contracts.pricing``
   - ``_buy_reference`` / ``_sell_reference`` / ``_confirmed_point`` → 转发到共享实现
   - 删掉因此变成死代码的 ``_h`` / ``_l`` / ``_direction`` / ``_to_raw``

2. emotion-core ``algorithms/levels.py``
   - 常量 → ``emotion_cpt.contracts.pricing``（**消掉手抄副本**）
   - ``_picks`` → 转发到共享实现
   - 取整位数：3 位 → **2 位**（``PRICE_ROUND_DIGITS``）
     ⇒ 口径收敛：同一只票两个系统不再印出不同的买/卖点价
     （实测 36 个价里 29 个原本不一致，最大差 0.005 元）
"""

from __future__ import annotations

import pathlib
import sys

CPT = pathlib.Path("/home/ubuntu/DSH/Chan_Pattern_Trader")
EMO = pathlib.Path("/home/ubuntu/DSH/emotion-core")


def patch_cpt() -> None:
    p = CPT / "cpt" / "application" / "track_points.py"
    s = p.read_text(encoding="utf-8")
    orig = s

    # ── ① 常量 → 共享契约 ──
    old_const = '''__all__ = [
    "BUY_BUFFER",
    "SELL_BUFFER",
    "STOP_LOSS_RATIO",
    "compute_points",
]

#: BUY reference 的缓冲：在算出的 raw 价上**再上调 2%**，给行情波动留余地
#: （基本面：中枢下沿是"触底即反弹"的参考，2% 缓冲避免刚好擦边进不去）
BUY_BUFFER: Final[float] = 1.02
#: SELL reference 的缓冲：在算出的 raw 价上**再下调 3%**
#: （阻力位附近"摸一下"是常态，3% 缓冲降低"差一分钱没到"的挫败）
SELL_BUFFER: Final[float] = 0.97
#: 止损相对 BUY reference 的比例
STOP_LOSS_RATIO: Final[float] = 0.95

#: 双向各取最近 N 笔 + 全部中枢（一般 1-2 个）
_BI_LOOKBACK: Final[int] = 3
_ZHONGSHU_LOOKBACK: Final[int] = 2
'''
    new_const = '''__all__ = [
    "BUY_BUFFER",
    "SELL_BUFFER",
    "STOP_LOSS_RATIO",
    "compute_points",
]

# ── 判据常量与算式本体已迁至 Emotion-CPT（2026-10-23）────────────────────
# 单一真源：emotion_cpt.contracts.pricing（常量）
#         emotion_cpt.snapshot.points（算式）
# 此前 emotion-core 侧各手抄了一份，常量与公式都可能漂 —— 现在两侧共用同一份。
from emotion_cpt.contracts.pricing import (  # noqa: E402
    BUY_BUFFER,
    SELL_BUFFER,
    STOP_LOSS_RATIO,
)
from emotion_cpt.snapshot.points import (  # noqa: E402
    confirmed_point as _shared_confirmed_point,
)
from emotion_cpt.snapshot.points import (  # noqa: E402
    structure_pick as _shared_structure_pick,
)
'''
    assert old_const in s, "CPT: 常量段未命中"
    s = s.replace(old_const, new_const, 1)

    # ── ② 删掉变成死代码的私有 helper ──
    dead = '''def _h(obj: Any) -> float | None:
    """结构对象的 ``high``（dict 或 dataclass 都认）。"""
    if obj is None:
        return None
    if isinstance(obj, dict):
        v = obj.get("high")
    else:
        v = getattr(obj, "high", None)
    return float(v) if v is not None else None


def _l(obj: Any) -> float | None:
    """结构对象的 ``low``。"""
    if obj is None:
        return None
    if isinstance(obj, dict):
        v = obj.get("low")
    else:
        v = getattr(obj, "low", None)
    return float(v) if v is not None else None


def _direction(obj: Any) -> int | None:
    """笔的方向 ``+1`` 向上 / ``-1`` 向下。"""
    if obj is None:
        return None
    if isinstance(obj, dict):
        v = obj.get("direction")
    else:
        v = getattr(obj, "direction", None)
    return int(v) if v is not None else None


def _to_raw(adjusted_price: float, price_ratio: float | None) -> float | None:
    """后复权 → raw。``price_ratio`` 不可用时返 None，不静默用错数。"""
    if price_ratio is None or price_ratio <= 0:
        return None
    return adjusted_price / price_ratio


'''
    assert dead in s, "CPT: 私有 helper 段未命中"
    s = s.replace(dead, "", 1)

    # ── ③ _buy_reference / _sell_reference → 转发 ──
    old_buy = '''    candidates: list[tuple[str, float]] = []
    for zs in zhongshus[-_ZHONGSHU_LOOKBACK:]:
        low = _l(zs)
        if low is not None:
            candidates.append((f"中枢下沿 {low:.2f}", low))

    for bi in bis[-_BI_LOOKBACK:]:
        # 向下笔的 low 才是"低点"参考（向上笔的 high 不算买点附近的参考）
        if _direction(bi) == -1:
            low = _l(bi)
            if low is not None:
                candidates.append((f"向下笔低点 {low:.2f}", low))

    if not candidates:
        return {
            "price_level": None,
            "condition": "无结构数据，刷新后再看",
            "rationale": "overlays.bis / zhongshus 为空（可能是 degraded snapshot）",
        }

    # 取最低（最保守：让价格真正下来才到）
    label, raw_adj = min(candidates, key=lambda x: x[1])
    raw_price = _to_raw(raw_adj, price_ratio)
    if raw_price is None:
        return None
    final = round(raw_price * BUY_BUFFER, 2)
    return {
        "price_level": final,'''
    new_buy = '''    # 算式本体在 Emotion-CPT（emotion_cpt.snapshot.points）—— 两侧单一真源。
    pick = _shared_structure_pick(
        {"zhongshus": zhongshus, "bis": bis}, price_ratio, "buy"
    )
    if pick.price_level is None:
        if pick.n_candidates == 0:
            # 没有结构数据 ⇒ 给出可展示的占位（与旧实现同形）
            return {
                "price_level": None,
                "condition": "无结构数据，刷新后再看",
                "rationale": pick.reason,
            }
        # 有候选但 ratio 无效 ⇒ 不给参考价（与旧实现同形：返回 None）
        return None
    label = pick.label or ""
    final = pick.price_level
    return {
        "price_level": final,'''
    assert old_buy in s, "CPT: _buy_reference 主体未命中"
    s = s.replace(old_buy, new_buy, 1)

    old_sell = '''    candidates: list[tuple[str, float]] = []
    for zs in zhongshus[-_ZHONGSHU_LOOKBACK:]:
        high = _h(zs)
        if high is not None:
            candidates.append((f"中枢上沿 {high:.2f}", high))

    for bi in bis[-_BI_LOOKBACK:]:
        if _direction(bi) == 1:
            high = _h(bi)
            if high is not None:
                candidates.append((f"向上笔高点 {high:.2f}", high))

    if not candidates:
        return {
            "price_level": None,
            "condition": "无结构数据，刷新后再看",
            "rationale": "overlays.bis / zhongshus 为空（可能是 degraded snapshot）",
        }

    # 取最高（最保守：等价格真正上去才卖）
    label, raw_adj = max(candidates, key=lambda x: x[1])
    raw_price = _to_raw(raw_adj, price_ratio)
    if raw_price is None:
        return None
    final = round(raw_price * SELL_BUFFER, 2)
    return {
        "price_level": final,'''
    new_sell = '''    pick = _shared_structure_pick(
        {"zhongshus": zhongshus, "bis": bis}, price_ratio, "sell"
    )
    if pick.price_level is None:
        if pick.n_candidates == 0:
            return {
                "price_level": None,
                "condition": "无结构数据，刷新后再看",
                "rationale": pick.reason,
            }
        return None
    label = pick.label or ""
    final = pick.price_level
    return {
        "price_level": final,'''
    assert old_sell in s, "CPT: _sell_reference 主体未命中"
    s = s.replace(old_sell, new_sell, 1)

    # ── ④ _confirmed_point → 转发 ──
    old_conf = '''    obj = last_zs if last_zs is not None else last_bi
    if obj is None:
        return None
    if side == "buy":
        adj = _l(obj)
        if adj is None:
            return None
        raw = _to_raw(adj, price_ratio)
        if raw is None:
            return None
        return {
            "price_level": round(raw, 2),
            "condition": "信号已经走到确认这一步，且价格仍在区间内",
            "rationale": f"取最新结构的下沿 {adj:.2f}（adjusted）÷ {price_ratio:.4f}",
        }
    if side == "sell":
        adj = _h(obj)
        if adj is None:
            return None
        raw = _to_raw(adj, price_ratio)
        if raw is None:
            return None
        return {
            "price_level": round(raw, 2),
            "condition": "信号已经走到确认这一步，且价格仍在区间内",
            "rationale": f"取最新结构的上沿 {adj:.2f}（adjusted）÷ {price_ratio:.4f}",
        }
    return None'''
    new_conf = '''    return _shared_confirmed_point(last_bi, last_zs, price_ratio, side)'''
    assert old_conf in s, "CPT: _confirmed_point 主体未命中"
    s = s.replace(old_conf, new_conf, 1)

    # ── ⑤ typing.Final 不再使用 ──
    s = s.replace("from typing import Any, Final\n", "from typing import Any\n", 1)

    assert s != orig
    p.write_text(s, encoding="utf-8")
    print("  ✓ CPT track_points.py 已改为转发")


def patch_emotion() -> None:
    p = EMO / "src" / "emotion_core" / "algorithms" / "levels.py"
    s = p.read_text(encoding="utf-8")
    orig = s

    old_head = '''from emotion_core.domain.holding import Levels

# ── 结构位常数：与 CPT track_points.py 同值（移植口径，勿单方面改） ──────────
STOP_LOSS_RATIO: Final[float] = 0.95  # track_points.py:49
BUY_BUFFER: Final[float] = 1.02  # track_points.py:44
SELL_BUFFER: Final[float] = 0.97  # track_points.py:47
BI_LOOKBACK: Final[int] = 3  # track_points.py:_BI_LOOKBACK
ZHONGSHU_LOOKBACK: Final[int] = 2  # track_points.py:_ZHONGSHU_LOOKBACK
'''
    new_head = '''from emotion_core.domain.holding import Levels

# ── 结构位常数与算式本体：单一真源在 Emotion-CPT（2026-10-23）──────────────
# 此前这里是**手抄** CPT track_points.py 的副本（连行号引用都已差 1 行），
# 改一边不传播、且没有任何测试会红。现改为 import 共享契约。
from emotion_cpt.contracts.pricing import (
    BI_LOOKBACK,
    BUY_BUFFER,
    PRICE_ROUND_DIGITS,
    SELL_BUFFER,
    STOP_LOSS_RATIO,
    ZHONGSHU_LOOKBACK,
)
from emotion_cpt.snapshot.points import structure_picks
'''
    assert old_head in s, "EMO: 常量段未命中"
    s = s.replace(old_head, new_head, 1)

    old_picks = '''def _picks(overlays: dict, ratio: float) -> tuple[float | None, float | None]:
    """从 overlays 取 raw 域的 (买结构位, 卖结构位)；无候选返回 (None, None)。"""
    zs = overlays.get("zhongshus")
    bis = overlays.get("bis")
    if not isinstance(zs, list) or not isinstance(bis, list):
        return None, None
    lows: list[float] = []
    highs: list[float] = []
    for z in zs[-ZHONGSHU_LOOKBACK:]:
        if isinstance(z, dict):
            lo, hi = _num(z.get("low")), _num(z.get("high"))
            if lo is not None:
                lows.append(lo)
            if hi is not None:
                highs.append(hi)
    for b in bis[-BI_LOOKBACK:]:
        if not isinstance(b, dict):
            continue
        if b.get("direction") == _DIR_DOWN:
            lo = _num(b.get("low"))
            if lo is not None:
                lows.append(lo)
        elif b.get("direction") == _DIR_UP:
            hi = _num(b.get("high"))
            if hi is not None:
                highs.append(hi)
    # adj → raw 必须除以 ratio（ratio 已由调用方校验为正）
    buy = min(lows) / ratio * BUY_BUFFER if lows else None
    sell = max(highs) / ratio * SELL_BUFFER if highs else None
    return buy, sell'''
    new_picks = '''def _picks(overlays: dict, ratio: float) -> tuple[float | None, float | None]:
    """从 overlays 取 raw 域的 (买结构位, 卖结构位)；无候选返回 (None, None)。

    ⚠️ 算式本体在 Emotion-CPT（``emotion_cpt.snapshot.points``）——
    与 CPT 的 ``track_points`` 共用同一份实现，不再各写一份。
    """
    return structure_picks(overlays, ratio)'''
    assert old_picks in s, "EMO: _picks 未命中"
    s = s.replace(old_picks, new_picks, 1)

    # 取整：3 位 → 2 位（PRICE_ROUND_DIGITS）
    s = s.replace('''                buy_reference=round(buy, 3) if buy is not None else None,
                stop_price=round(stop, 3) if stop is not None else None,
                target_price=round(sell, 3) if sell is not None else None,''',
'''                buy_reference=buy,
                stop_price=round(stop, PRICE_ROUND_DIGITS) if stop is not None else None,
                target_price=sell,''')
    s = s.replace(
        '''                sell_reference=round(sell, 3) if sell is not None else None,''',
'''                sell_reference=sell,''')
    s = s.replace('''            buy_reference=round(raw_close * (1 - FALLBACK_BUY_PCT), 3),
            stop_price=round(raw_close * (1 - FALLBACK_STOP_PCT), 3),
            target_price=round(raw_close * (1 + FALLBACK_TARGET_PCT), 3),''',
'''            buy_reference=round(raw_close * (1 - FALLBACK_BUY_PCT), PRICE_ROUND_DIGITS),
            stop_price=round(raw_close * (1 - FALLBACK_STOP_PCT), PRICE_ROUND_DIGITS),
            target_price=round(raw_close * (1 + FALLBACK_TARGET_PCT), PRICE_ROUND_DIGITS),''')
    s = s.replace('''        sell_reference=round(raw_close * (1 + FALLBACK_TARGET_PCT), 3),''',
'''        sell_reference=round(raw_close * (1 + FALLBACK_TARGET_PCT), PRICE_ROUND_DIGITS),''')

    # 模块 docstring：说明算式已迁走
    s = s.replace(
        '''结构位算式**逐条移植**自 CPT（Chan_Pattern_Trader）
的 `application/track_points.py`，
**不 import**（`docs/shared-tables-contract.md` §5 明令两侧零代码依赖）：''',
'''结构位算式**已于 2026-10-23 迁至 Emotion-CPT**（`emotion_cpt.snapshot.points`），
本模块与 CPT 的 `application/track_points.py` **共用同一份实现**：

- 此前这里是 CPT 的**手抄副本**（连行号引用都差 1 行），改一边不传播、无测试会红；
- 现在公式、常量、取整位数（2 位）**单一真源** ⇒
  同一只票在两个系统印出的买/卖点价**一致**（实测原先 36 个价里 29 个不一致）。''')

    assert s != orig
    p.write_text(s, encoding="utf-8")
    print("  ✓ emotion-core levels.py 已改为转发 + 取整收敛到 2 位")


def patch_emotion_pyproject() -> None:
    p = EMO / "pyproject.toml"
    s = p.read_text(encoding="utf-8")
    if "emotion-cpt" in s:
        print("  (emotion-core pyproject 已声明 emotion-cpt,跳过)")
        return
    old = "dependencies = []"
    new = (
        "dependencies = [\n"
        "    # 判据（结构位算式与常量）已迁至 Emotion-CPT —— "
        "单向依赖：emotion_core → emotion_cpt。\n"
        "    # 钉到 tag 而不是 main：main 是移动目标，重建环境会拿到不确定的判据版本。\n"
        '    "emotion-cpt @ git+https://github.com/nxz1026/Emotion-CPT.git@v0.1.0",\n'
        "]"
    )
    assert old in s, "EMO: pyproject dependencies 未命中"
    p.write_text(s.replace(old, new, 1), encoding="utf-8")
    print("  ✓ emotion-core pyproject 已声明 emotion-cpt 依赖")


def main() -> int:
    patch_cpt()
    patch_emotion()
    patch_emotion_pyproject()
    return 0


if __name__ == "__main__":
    sys.exit(main())
