"""笔的力度度量与门槛合并口径的判据级测试。

对应审计 39 条里的两条**致命**项：

- **#1** ``build_bis`` 从不填 ``power_price`` / ``power_volume`` / ``length``
  ⇒ 本仓自己产出的笔喂给 ``check_first_buy`` 必然抛 ``ValueError``
  （"算不出来"，不是"算错"）。
- **#2** ``min_bi_len`` 顺延时**丢失被吸收端点的极值** ⇒ 笔的 high/low
  系统性偏小 ⇒ 中枢 ``zg/zd`` 偏小、背驰分母同步错位。

力度口径的**外部真源**是 czsc 1.0.1 原生包：2026-10-25 用它在随机行情上
逐笔对账实测，``power_price == round(high - low, 2)`` **零例外**，
且合并笔的 high/low **包含被吸收端点的极值**（"仅两端"口径 11 例全错）。
这里把那条实测结论固化成断言。
"""

from __future__ import annotations

import pytest

from emotion_cpt.contracts.pricing import round_to_2_digit
from emotion_cpt.structure.bi import build_bis, power_metrics
from emotion_cpt.structure.contain import merge_contained_bars
from emotion_cpt.structure.first_buy import check_first_buy
from emotion_cpt.structure.fractal import detect_fractals
from emotion_cpt.structure.models import CanonicalBar

_BAR_MS = 60_000
_START_MS = 1_700_000_000_000


def _bars(specs: list[tuple[float, float, float]]) -> list[CanonicalBar]:
    """按 ``(high, low, volume)`` 造一串 1 分钟 K 线（open=close=区间中价）。

    中价只是为了填满 ``CanonicalBar`` 的必填字段 —— 分型识别只看高低。
    """
    out: list[CanonicalBar] = []
    open_time = _START_MS
    for high, low, volume in specs:
        mid = (high + low) / 2
        out.append(
            CanonicalBar(
                open_time=open_time,
                open=mid,
                high=high,
                low=low,
                close=mid,
                volume=volume,
                close_time=open_time + _BAR_MS - 1,
                quote_volume=volume * mid,
                trade_count=1,
                taker_buy_base_volume=volume / 2,
                taker_buy_quote_volume=volume * mid / 2,
                is_closed=True,
            )
        )
        open_time += _BAR_MS
    return out


#: 一个**向上**笔：底分型@1 → 顶分型@4（中间 bar 2/3 的量能参与 power_volume）。
_UP_SPECS: list[tuple[float, float, float]] = [
    (12.0, 10.0, 100.0),
    (11.0, 9.0, 200.0),
    (13.0, 11.0, 300.0),
    (14.0, 12.0, 400.0),
    (15.0, 13.0, 500.0),
    (13.0, 11.0, 600.0),
    (12.0, 10.0, 700.0),
]

#: 一个**向下**笔：顶分型@1 → 底分型@4（一买判定的方向）。
_DOWN_SPECS: list[tuple[float, float, float]] = [
    (13.0, 11.0, 100.0),
    (15.0, 13.0, 200.0),
    (12.0, 10.0, 300.0),
    (11.0, 9.0, 400.0),
    (10.0, 8.0, 500.0),
    (13.0, 11.0, 600.0),
]

#: 门槛合并用例：底@1 → 顶@3 → 底@5 → 顶@8。
#: 第一笔（底@1→顶@3）跨度只有 3 < min_bi_len ⇒ 终点顺延到顶@8，
#: 被吸收的是 **顶@3（high=22，比两端都高）**。
_MERGE_SPECS: list[tuple[float, float, float]] = [
    (12.0, 10.0, 100.0),
    (11.0, 9.0, 200.0),
    (14.0, 12.0, 300.0),
    (22.0, 20.0, 400.0),
    (15.0, 13.0, 500.0),
    (13.0, 11.0, 600.0),
    (14.0, 12.0, 700.0),
    (15.0, 13.0, 800.0),
    (16.0, 14.0, 900.0),
    (13.0, 11.0, 1000.0),
]


def test_fixture_bars_are_not_merged() -> None:
    """前提：三组 fixture 的 K 线**互不包含** ⇒ 去包含后根数 == 原始根数。

    断言写死在这里，是为了让"下标算错了"这种错误**当场报出来**，
    而不是让后面的 length / volume 断言变得含义不明。
    """
    for specs in (_UP_SPECS, _DOWN_SPECS, _MERGE_SPECS):
        bars = _bars(specs)
        merged = merge_contained_bars(bars)
        assert len(merged) == len(bars), "fixture 的 K 线不该发生包含合并"


def test_power_metrics_filled_when_bars_given() -> None:
    """给了 ``bars`` ⇒ 三件力度度量**齐备**，且与 czsc 口径一致。"""
    bars = _bars(_UP_SPECS)
    fractals = detect_fractals(bars, level=0)
    bis = build_bis(fractals, level=0, bars=bars)

    assert len(bis) == 1
    bi = bis[0]
    # length = 去包含后根数（端点 merged_index 1..4 ⇒ 4 根）
    assert bi.length == 4
    # power_price = 笔的**振幅**（不是两端分型价格之差）
    assert bi.high == 15.0
    assert bi.low == 9.0
    assert bi.power_price == round_to_2_digit(bi.high - bi.low) == 6.0
    # power_volume = 中间 bar（2/3）的量能之和，**不含两端**
    assert bi.power_volume == 300.0 + 400.0


def test_power_metrics_stay_unfilled_without_bars() -> None:
    """不给 ``bars`` ⇒ 力度度量**保持未填充**（不是半填）。

    半填（length 有值、量能是 0）会被 ``_require_power_metrics`` 放过去
    ⇒ 背驰判定静默失真（量能恒 0 ⇒「量能变小」恒成立 ⇒ 恒判背驰）。
    """
    bars = _bars(_UP_SPECS)
    fractals = detect_fractals(bars, level=0)
    bi = build_bis(fractals, level=0)[0]

    assert bi.length == 0
    assert bi.power_price == 0.0
    assert bi.power_volume == 0.0


def test_unfilled_metrics_make_first_buy_fail_loudly() -> None:
    """未填充的笔喂给 ``check_first_buy`` ⇒ **响亮报错**，不是静默 False。

    这条是"宁可报错也不拿 0 去比较"的纪律本身。
    """
    bars = _bars(_DOWN_SPECS)
    fractals = detect_fractals(bars, level=0)
    bis = build_bis(fractals, level=0)

    assert bis[0].direction == -1, "fixture 应产生一个向下笔（一买方向）"
    with pytest.raises(ValueError, match="力度度量未填充"):
        check_first_buy(bis)


def test_merged_bi_keeps_absorbed_anchor_extremes() -> None:
    """门槛顺延时，被吸收端点的极值**属于这笔的区间**（审计 #2）。

    fixture 里被吸收的顶分型 high=22，比两端都高 ⇒ 只看两端会把笔的
    high 算成 16（偏小 ⇒ 中枢 zg/zd 偏小、背驰分母同步错位）。
    """
    bars = _bars(_MERGE_SPECS)
    fractals = detect_fractals(bars, level=0)
    bis = build_bis(fractals, level=0, min_bi_len=4, bars=bars)

    assert len(bis) == 1, "第一笔跨度不足 ⇒ 终点顺延 ⇒ 只剩一笔"
    bi = bis[0]
    assert bi.high == 22.0, "笔的高点必须覆盖被吸收的顶分型"
    assert bi.low == 9.0
    # 力度度量随之变化：振幅按**整段区间**算
    assert bi.power_price == round_to_2_digit(bi.high - bi.low) == 13.0
    # length = 端点 merged_index 跨度（1..8 ⇒ 8 根）
    assert bi.length == 8
    # power_volume = 中间 bar 2..7 的量能（不含两端）
    assert bi.power_volume == 300.0 + 400.0 + 500.0 + 600.0 + 700.0 + 800.0


def test_merged_bi_span_uses_merged_index_not_bar_index() -> None:
    """门槛量纲仍是「去包含后根数」，改极值口径**没有**动它。"""
    bars = _bars(_MERGE_SPECS)
    fractals = detect_fractals(bars, level=0)
    bis = build_bis(fractals, level=0, min_bi_len=4)
    assert len(bis) == 1
    # 端点 merged_index 1 → 8 ⇒ 跨度 8 ≥ 4 ⇒ 门槛成立
    assert bis[0].start_time == _START_MS + _BAR_MS
    assert bis[0].end_time == _START_MS + 8 * _BAR_MS + _BAR_MS - 1


def test_power_metrics_rejects_out_of_range_index() -> None:
    """端点下标越界 ⇒ 报错（量纲错位时宁可报错）。"""
    bars = _bars(_UP_SPECS)
    with pytest.raises(ValueError, match="越界"):
        power_metrics(1.0, 0.0, start_index=0, end_index=99, bars=bars)


def test_power_metrics_requires_volume() -> None:
    """K 线没有 ``volume`` ⇒ 报错（BarLike 协议不承诺量能）。"""

    class _NoVolume:
        open_time = 0
        close_time = 1
        high = 2.0
        low = 1.0
        direction = 1

    with pytest.raises(TypeError, match="volume"):
        power_metrics(
            2.0, 1.0, start_index=0, end_index=2, bars=[_NoVolume(), _NoVolume(), _NoVolume()]
        )
