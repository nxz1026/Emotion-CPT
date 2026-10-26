"""★ 涨停价/板制口径的**三方穷举等价**验证。

三方：

1. **新统一实现** ``emotion_cpt.structure.price``（整数分）
2. **emotion-core 现实现** ``emotion_core.utils.price``（整数分）
3. **CPT 现实现** ``emotion_cpt.structure.intraday_rules``（Decimal + ROUND_HALF_UP）

前两者**必须逐分相同**（同一个算法）。
第三者是**不同算法**（Decimal vs 整数分）⇒ 必须**逐分等价**（结果相同）。

⚠️ 「等价」不是「相同实现」—— 这正是本次统一的目的：
把**同一口径的两套实现**合成一份，同时保证**数值一个字都不变**。

样本：全市场常见分位 × 各板块 × ST/非 ST × 边界分位（.005 / .495 / .995 等）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from emotion_cpt.structure import intraday_rules
from emotion_cpt.structure import price as new

#: 生产上抽样覆盖到的代码（各板块 + ST 名）
_CODES = (
    "600519",  # 沪主板
    "601318",  # 沪主板
    "000001",  # 深主板
    "002594",  # 深主板（比亚迪）
    "300750",  # 创业板
    "301718",  # 创业板
    "688981",  # 科创板
    "688111",  # 科创板
    "920296",  # 北交所
    "430047",  # 北交所 43 段
    "830799",  # 北交所 83 段
    "873223",  # 北交所 87 段
)
_NAMES = (None, "贵州茅台", "*ST康佳", "ST某某", "ST 紫晶", "北方华创")
#: 昨收分位：含大量 .5 边界（ROUND_HALF_UP 的考验点）
_CENTS = (
    1, 5, 10, 50, 99, 100, 105, 195, 200, 285, 500, 995, 1000, 1005, 1105,
    1234, 1995, 2000, 2505, 3333, 5000, 9995, 10000, 12345, 54321, 99999, 100000,
    10405, 10595, 11005, 12095, 13005, 14095, 20005, 30005,
)


def _emotion_price():
    """emotion-core 的现实现（若该仓在机器上）。"""
    root = Path("/home/ubuntu/DSH/emotion-core/src")
    if not (root / "emotion_core" / "utils" / "price.py").exists():
        pytest.skip("emotion-core 仓不在本机")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from emotion_core.utils import price as emo

    return emo


def _cpt_rules():
    """CPT 那份（Decimal 实现，已在本仓）。"""
    from emotion_cpt.structure import intraday_rules

    return intraday_rules


def test_board_pct_milli_matches_emotion():
    emo = _emotion_price()
    for code in _CODES:
        assert new.board_pct_milli(code) == emo.board_pct_milli(code), code


def test_limit_up_price_cents_matches_emotion_exhaustively():
    """★ 整数分实现必须与 emotion 现实现**逐分相同**。"""
    emo = _emotion_price()
    for code in _CODES:
        for cents in _CENTS:
            got = new.limit_up_price_cents(cents, code)
            want = emo.limit_up_price_cents(cents, code)
            assert got == want, f"{code} @ {cents}分: {got} != {want}"


def test_limit_down_price_cents_matches_emotion_exhaustively():
    emo = _emotion_price()
    for code in _CODES:
        for cents in _CENTS:
            got = new.limit_down_price_cents(cents, code)
            want = emo.limit_down_price_cents(cents, code)
            assert got == want, f"{code} @ {cents}分: {got} != {want}"


def test_limit_up_price_cents_with_st_override_matches_emotion():
    """ST 靠名字 ⇒ 走 pct_milli 覆盖。"""
    emo = _emotion_price()
    for code in _CODES:
        for name in _NAMES:
            for cents in _CENTS:
                pct = new.pct_milli_for(code, name=name)
                got = new.limit_up_price_cents(cents, code, pct_milli=pct)
                want = emo.limit_up_price_cents(cents, code, pct_milli=pct)
                assert got == want, f"{code}/{name} @ {cents}分: {got} != {want}"


def test_limit_up_price_equals_cpt_decimal_implementation():
    """★ 新实现（整数分）必须与 CPT 那份（Decimal）**逐分等价**。

    这是跨仓对账的加强版：以前是两个仓各写一份、靠对账测试比对；
    现在是**同一个仓里的两个算法**，可以穷举到分。
    """
    cpt = _cpt_rules()
    for code in _CODES:
        for name in _NAMES:
            for cents in _CENTS:
                pre_close = cents / 100
                got = new.limit_up_price(code, pre_close, name=name)
                want = cpt.limit_up_price(code, pre_close, name=name)
                assert got == want, f"{code}/{name} @ {pre_close}: {got} != {want}"


def test_board_pct_limit_matches_cpt_implementation():
    """板制判定（名字感知）必须与 CPT 那份一致。"""
    cpt = _cpt_rules()
    for code in _CODES:
        for name in _NAMES:
            assert new.board_pct_limit(code, name=name) == cpt.board_pct_limit(code, name=name)


def test_is_st_name_matches_cpt_implementation():
    cpt = _cpt_rules()
    for name in _NAMES:
        assert new.is_st_name(name) == cpt.is_st_name(name)


def test_bse_st_is_thirty_percent():
    """⛔ 北交所 ST 是 30%，不是 5% 也不是 20%。

    这正是当年把「已封板」误判成「未到板」的那个坑。
    """
    assert new.board_pct_limit("920296", name="ST某某") == 30.0
    assert new.board_pct_limit("430047", name="*ST康佳") == 30.0
    assert new.board_pct_limit("600519", name="*ST康佳") == 5.0
    assert new.board_pct_limit("300750", name="ST某某") == 20.0


def test_shares_per_lot_is_hundred():
    assert intraday_rules.SHARES_PER_LOT == 100
