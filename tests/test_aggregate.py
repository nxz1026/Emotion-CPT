"""聚合页的**纯逻辑**测试（不发请求）。

⚠️ 2026-10-24：原先这里测的是 `_picks` 的手抄实现（情绪侧口径），
现已迁到 ``emotion_cpt.snapshot.points``（统一实现），
本文件改为测**三套口径的并排与差异检测**（见 ``test_web_aggregate.py``）。
"""

from __future__ import annotations

from emotion_cpt.snapshot.points import structure_picks


def test_structure_picks_is_the_single_implementation():
    """结构位算式的唯一实现点（CPT 与 emotion-core 都从这里取）。"""
    overlays = {
        "zhongshus": [{"low": 1300.0, "high": 1308.88}],
        "bis": [{"direction": -1, "low": 1248.10, "high": 1260.0}],
    }
    buy, sell = structure_picks(overlays, 0.8765)
    assert buy is not None and sell is not None
    # 买 = 最低候选 1248.10 ÷ 0.8765 × 1.02；卖 = 最高候选 1308.88 ÷ 0.8765 × 0.97
    assert abs(buy - round(1248.10 / 0.8765 * 1.02, 2)) < 1e-9
    assert abs(sell - round(1308.88 / 0.8765 * 0.97, 2)) < 1e-9


def test_structure_picks_without_ratio_gives_none():
    """ratio 无效 ⇒ 不给结构位（绝不拿 adj 域充数）。"""
    overlays = {"zhongshus": [{"low": 1.0, "high": 2.0}], "bis": []}
    assert structure_picks(overlays, None) == (None, None)
    assert structure_picks(overlays, 0.0) == (None, None)


def test_structure_picks_without_overlays_gives_none():
    assert structure_picks({}, 1.0) == (None, None)
    assert structure_picks(None, 1.0) == (None, None)
