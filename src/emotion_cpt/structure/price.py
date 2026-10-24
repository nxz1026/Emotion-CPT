"""A 股板制与涨跌停价 —— **全系统唯一实现**。

## 为什么在这个仓

此前**两套实现并存**：

- emotion-core ``utils/price.py`` —— 整数分运算（``(x*1000+pct+500)//1000``），
  覆盖涨停/跌停/``is_limit_up``/``is_limit_down``；仓内还有一条 AST 门禁
  （``tests/caliber/test_price_unique_impl.py``）禁止出现第二套。
- CPT ``cpt/domain/intraday_rules.py``（2026-10-24 已随判据内核搬进本仓）——
  ``Decimal`` + ``ROUND_HALF_UP``，只覆盖涨停价。

两边数值等价（跨仓对账用例穷举过 3000 个分位 × 11 个代码，0 差异），
但**两套实现**本身就是 emotion-core 那条门禁要防的事 —— 它防得住仓内，防不住跨仓。

⇒ 现在唯一实现在这里：**emotion-core 与 CPT 都从这里取**。

## 算法选型：整数分，不是 Decimal

选 emotion-core 的整数分式，理由三条：

1. **无浮点** —— ``(x*1000 + pct + 500) // 1000`` 全程整数，没有 ``0.1+0.2`` 那类误差；
2. **与生产 SQL 逐分一致** —— 生产 ``derive.py`` 的 SQL 整数式
   ``up_c = (round(pre_close*100)::bigint * pct + 50) / 100`` 与它同源；
3. **覆盖面更广** —— 跌停价与 ``is_limit_up``/``is_limit_down`` 只有这一份有。

CPT 的 ``Decimal`` 版作为**对照实现**保留在本仓
（:mod:`emotion_cpt.structure.intraday_rules`），并由
``tests/test_price_equivalence.py`` 穷举验证两者逐分一致。

## 口径：判定顺序即口径

⛔ **顺序不能改**：

1. 创业板 300/301、科创板 688/689 → 20%（**ST 也是 20%**）
2. 北交所 920/8/4 → 30%（**ST 也是 30%** —— 北交所没有 5% 档）
3. 主板 ST → 5%
4. 其余 → 10%

历史上踩过：把 ST 提到最前 ⇒ 北交所 ST 落到 20%，算出**偏低的涨停价**，
于是「已经封板」被误判成「还没到板」—— **方向比漏报更糟**。
"""

from __future__ import annotations

from typing import Final

#: 主板涨跌幅（%）
BOARD_PCT_MAIN: Final[float] = 10.0
#: 创业板 / 科创板涨跌幅（%）
BOARD_PCT_GROWTH: Final[float] = 20.0
#: 北交所涨跌幅（%）
BOARD_PCT_BSE: Final[float] = 30.0
#: 主板 ST 涨跌幅（%）
BOARD_PCT_ST: Final[float] = 5.0

#: 一手 = 100 股
SHARES_PER_LOT: Final[int] = 100

#: 创业板 / 科创板代码前缀
_GROWTH_PREFIXES: Final[tuple[str, ...]] = ("300", "301", "688", "689")
#: 北交所代码前缀
_BSE_PREFIXES: Final[tuple[str, ...]] = ("920", "8", "4")
#: 沪深主板代码前缀
_MAIN_PREFIXES: Final[tuple[str, ...]] = ("600", "601", "603", "605", "000", "001", "002", "003")

#: 涨跌幅的千分比：主板 100 = 10.0%
_PCT_MILLI_MAIN: Final[int] = 100
_PCT_MILLI_GROWTH: Final[int] = 200
_PCT_MILLI_BSE: Final[int] = 300


def is_st_name(name: str | None) -> bool:
    """名字里带 ST 就是 ST。**只能靠名字** —— 代码里没有任何 ST 信息。"""
    if not name:
        return False
    return "ST" in name.upper()


def is_main_board(code: str) -> bool:
    """是不是沪深主板。"""
    return code.strip().startswith(_MAIN_PREFIXES)


def board_of(code: str, *, name: str | None = None) -> str:
    """板块名（判据用枚举）：``main`` / ``growth`` / ``bse`` / ``st_main`` / ``st_growth``。

    ⛔ 顺序即口径：growth → bse → st_main → main。
    """
    code = code.strip()
    st = is_st_name(name)
    if code.startswith(_GROWTH_PREFIXES):
        return "st_growth" if st else "growth"
    if code.startswith(_BSE_PREFIXES):
        return "bse"
    if st:
        return "st_main"
    return "main"


def board_pct_limit(code: str, *, name: str | None = None) -> float:
    """这只票的涨跌停幅度（百分比）。

    :param name: 判断主板 ST **必须**传它（代码里分不出 ST）。
        不传按「非 ST」算 —— 这是**有意的乐观**：漏判 ST 得出偏高的涨停价
        （判不出封板、少报），而不是偏低的（假封板、错报）。宁可少报不可错报。
    """
    board = board_of(code, name=name)
    if board == "st_main":
        return BOARD_PCT_ST
    if board in ("growth", "st_growth"):
        return BOARD_PCT_GROWTH
    if board == "bse":
        return BOARD_PCT_BSE
    return BOARD_PCT_MAIN


def board_pct_milli(code: str) -> int:
    """涨跌幅的千分比（主板 100 = 10.0%，创业/科创 200 = 20%，北交所 300 = 30%）。

    ⚠️ **不含 ST** —— 代码里分不出 ST。ST 走
    :func:`board_pct_limit`（要名字）再转千分比。

    北交所代码格式：纯代码 4/8/920 开头，或 akshare symbol 前缀 ``bj``。
    """
    if code.startswith("bj"):
        return _PCT_MILLI_BSE
    if code.startswith(("30", "68")):
        return _PCT_MILLI_GROWTH
    if code.startswith(("4", "8", "92")):
        return _PCT_MILLI_BSE
    return _PCT_MILLI_MAIN


def pct_milli_for(code: str, *, name: str | None = None) -> int:
    """这只票的涨跌幅千分比，**ST 感知**（有名字就用名字判 ST）。"""
    if name is not None and is_st_name(name):
        # 主板 ST 是 5%；创业板/科创 ST 是 20%；北交所 ST 是 30%。
        pct = board_pct_limit(code, name=name)
        return int(round(pct * 10))
    return board_pct_milli(code)


def limit_up_price_cents(
    pre_close_cents: int, code: str, *, pct_milli: int | None = None
) -> int:
    """涨停价（分）。四舍五入与 SQL ``(x*pct + 50)/100`` 一致。

    :param pre_close_cents: 昨收价，单位分（int）
    :param pct_milli: 覆盖按代码推断的涨跌幅千分比（**只有 ST 需要**）
    """
    pct = board_pct_milli(code) if pct_milli is None else pct_milli
    return (pre_close_cents * (1000 + pct) + 500) // 1000


def limit_down_price_cents(
    pre_close_cents: int, code: str, *, pct_milli: int | None = None
) -> int:
    """跌停价（分）。``pct_milli`` 同 :func:`limit_up_price_cents`。"""
    pct = board_pct_milli(code) if pct_milli is None else pct_milli
    return (pre_close_cents * (1000 - pct) + 500) // 1000


def is_limit_up(close_cents: int, pre_close_cents: int, code: str) -> bool:
    """是否涨停（收盘 == 涨停价）。

    ⚠️ 用**精确等于**（``c_c == up_c``），不是 ``>=`` —— 逐字沿用 lkl 语义。
    """
    return close_cents == limit_up_price_cents(pre_close_cents, code)


def is_limit_down(close_cents: int, pre_close_cents: int, code: str) -> bool:
    """是否跌停（收盘 == 跌停价）。同样是精确等于。"""
    return close_cents == limit_down_price_cents(pre_close_cents, code)


def limit_up_price(code: str, pre_close: float, *, name: str | None = None) -> float | None:
    """涨停价（元）。

    :param name: 判断主板 ST **必须**传它（代码里分不出 ST）。
    :returns: 涨停价；``pre_close`` 缺失或 ≤0 时返回 ``None``（**不拍一个数**）。
    """
    if pre_close is None or pre_close <= 0:
        return None
    pct_milli = pct_milli_for(code, name=name)
    cents = limit_up_price_cents(int(round(pre_close * 100)), code, pct_milli=pct_milli)
    return cents / 100


__all__ = (
    "BOARD_PCT_BSE",
    "BOARD_PCT_GROWTH",
    "BOARD_PCT_MAIN",
    "BOARD_PCT_ST",
    "SHARES_PER_LOT",
    "board_of",
    "board_pct_limit",
    "board_pct_milli",
    "is_limit_down",
    "is_limit_up",
    "is_main_board",
    "is_st_name",
    "limit_down_price_cents",
    "limit_up_price",
    "limit_up_price_cents",
    "pct_milli_for",
)
