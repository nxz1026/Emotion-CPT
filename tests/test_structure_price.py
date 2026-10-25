"""A 股板制 / 涨跌停判据的判据级测试。

对应审计里的两条：

- **#3** ``is_limit_up`` / ``is_limit_down`` **既不收 name 也不收 pct_milli**
  ⇒ 主板 ST 永远按 10% 判 ⇒ ST 股 5% 封板判 ``False``（漏报），
  而 API 面**不存在**任何正确用法（``limit_up_price_cents`` 明明支持覆盖）。
- **#5** ``board_of`` 不认 akshare 的 ``bj`` 前缀 ⇒ 北交所票落到 ``main``
  ⇒ 与 ``board_pct_milli``（认 ``bj`` ⇒ 30%）**给出相反答案**
  ⇒ 涨停价差 2.29 元 ⇒「已封板」被误判成「未到板」。
"""

from __future__ import annotations

from emotion_cpt.structure.price import (
    BOARD_PCT_BSE,
    BOARD_PCT_GROWTH,
    BOARD_PCT_MAIN,
    BOARD_PCT_ST,
    board_of,
    board_pct_limit,
    board_pct_milli,
    is_limit_down,
    is_limit_up,
    limit_up_price_cents,
    pct_milli_for,
)

#: 昨收 100.00 元 = 10000 分
_PRE_CLOSE_CENTS = 10_000


def test_main_board_limit_up_price() -> None:
    """主板非 ST：10%。"""
    assert board_pct_limit("000001") == BOARD_PCT_MAIN
    assert limit_up_price_cents(_PRE_CLOSE_CENTS, "000001") == 11_000


def test_st_main_board_uses_five_percent() -> None:
    """主板 ST：5%。``name`` 是唯一能判 ST 的入口（代码里分不出 ST）。"""
    assert board_of("000001", name="ST平安") == "st_main"
    assert board_pct_limit("000001", name="ST平安") == BOARD_PCT_ST
    assert pct_milli_for("000001", name="ST平安") == 50
    assert limit_up_price_cents(_PRE_CLOSE_CENTS, "000001", pct_milli=50) == 10_500


def test_st_growth_board_keeps_twenty_percent() -> None:
    """创业板 ST 仍是 20%（口径：ST 只降主板那一档）。"""
    assert board_of("300750", name="ST宁德") == "st_growth"
    assert board_pct_limit("300750", name="ST宁德") == BOARD_PCT_GROWTH
    assert pct_milli_for("300750", name="ST宁德") == 200


def test_st_bse_board_keeps_thirty_percent() -> None:
    """北交所 ST 仍是 30%（北交所没有 5% 档）。"""
    assert board_of("920296", name="ST文峰") == "bse"
    assert board_pct_limit("920296", name="ST文峰") == BOARD_PCT_BSE
    assert pct_milli_for("920296", name="ST文峰") == 300


def test_is_limit_up_detects_st_seal() -> None:
    """审计 #3：ST 股 5% 封板必须判 True（此前按 10% 判 ⇒ 漏报）。"""
    assert is_limit_up(10_500, _PRE_CLOSE_CENTS, "000001", name="ST平安") is True
    # 10% 的价不是 ST 的涨停价 ⇒ 不该判 True
    assert is_limit_up(11_000, _PRE_CLOSE_CENTS, "000001", name="ST平安") is False


def test_is_limit_down_detects_st_seal() -> None:
    """ST 股 5% 跌停同样必须判 True。"""
    assert is_limit_down(9_500, _PRE_CLOSE_CENTS, "000001", name="ST平安") is True
    assert is_limit_down(9_000, _PRE_CLOSE_CENTS, "000001", name="ST平安") is False


def test_is_limit_up_accepts_pct_milli_override() -> None:
    """``pct_milli`` 覆盖：不需要名字也能判 ST（调用方已知幅度时）。"""
    assert is_limit_up(10_500, _PRE_CLOSE_CENTS, "000001", pct_milli=50) is True
    assert is_limit_down(9_500, _PRE_CLOSE_CENTS, "000001", pct_milli=50) is True


def test_is_limit_up_without_name_keeps_optimistic_behaviour() -> None:
    """不传 ``name`` ⇒ 仍按「非 ST」算（**有意的乐观**：宁可少报不可错报）。

    这条把"不传名字"的行为钉死，避免以后有人把默认改成 ST 口径
    ⇒ 主板票被当成 ST ⇒ 涨停价偏低 ⇒「已封板」误判成「未到板」。
    """
    assert is_limit_up(11_000, _PRE_CLOSE_CENTS, "000001") is True
    assert is_limit_up(10_500, _PRE_CLOSE_CENTS, "000001") is False


def test_bse_prefix_is_stripped_consistently() -> None:
    """审计 #5：``bj`` 前缀在两个 API 上必须给**同一个**答案。"""
    assert board_of("bj920296") == "bse"
    assert board_pct_milli("bj920296") == 300
    assert board_pct_limit("bj920296") == BOARD_PCT_BSE
    # 与纯代码口径一致
    assert board_of("bj920296") == board_of("920296")
    assert board_pct_milli("bj920296") == board_pct_milli("920296")


def test_whitespace_does_not_change_board() -> None:
    """空白必须被剥掉：此前两个 API 一个剥一个不剥 ⇒ 同一只票两个板块。"""
    assert board_pct_milli(" 300750") == board_pct_milli("300750")
    assert board_of(" 300750") == board_of("300750")
    assert board_pct_milli(" 000001") == 100


def test_bse_st_limit_price_is_not_main_board_price() -> None:
    """北交所票的涨停价不能按主板算（差 2.29 元 ⇒ 封板判定翻转）。"""
    bse = limit_up_price_cents(_PRE_CLOSE_CENTS, "bj920296")
    main = limit_up_price_cents(_PRE_CLOSE_CENTS, "000001")
    assert bse == 13_000
    assert main == 11_000
    assert bse != main


def test_unknown_code_falls_back_to_main_board() -> None:
    """未知代码 ⇒ 落到主板口径（**不猜**别的板块）。

    口径钉在这里：调用方拿到一只没见过的代码时，默认按主板 10% 处理，
    而不是报错或猜成北交所。
    """
    assert board_of("123456") == "main"
    assert board_pct_limit("123456") == BOARD_PCT_MAIN
    assert board_of("123456", name="ST某") == "st_main"
    assert board_pct_limit("123456", name="ST某") == BOARD_PCT_ST
