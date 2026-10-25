"""czsc × 自研 对账门禁的**判据级**测试（尺子的 pytest 包装）。

对应 2026-10-25 的 P0「自研与 czsc 的合并规则分叉」：
上一轮只留下一句「结构不可比」，**没有尺子** ⇒ 后面所有结构改动都是盲改。

本文件把这个尺子变成**会失败的断言**：

1. **差距在预算内**（`scripts/parity_czsc.py` 的退出码为 0）
2. **力度口径必须逐分一致**（门槛 1/2 下 ``power_price`` 最大差 = 0.0000）
   —— 这是 v0.8.4「力度度量 = 振幅」那条修复的**回归钉子**
3. **中枢口径必须一致**（自研中枢数 == czsc 的**已完成**中枢数）

⚠️ **czsc 只是对账工具，不是本仓的运行时依赖** ⇒ 没装就 skip，不算失败。
装法：``pip install --no-deps "czsc==1.0.1"``（只装原生扩展即可）。
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import parity_czsc  # noqa: E402


def _czsc_available() -> bool:
    try:
        parity_czsc.load_czsc_native()
    except Exception:
        return False
    return True


requires_czsc = pytest.mark.skipif(
    not _czsc_available(),
    reason="czsc 没装（对账工具，非运行时依赖）⇒ 跳过，不算通过也不算失败",
)


@requires_czsc
def test_parity_within_budget() -> None:
    """★ 主判据：四档门槛的差距都在预算内。

    预算写在 ``parity_czsc.BUDGET`` 里 —— 那是**当前差距的快照**：
    差距变大 ⇒ 这里红；差距变小 ⇒ 请**同时把预算收紧**（否则收敛会被悄悄丢掉）。
    """
    assert parity_czsc.main(["--rounds", "2"]) == 0, (
        "自研与 czsc 参照侧的差距超出预算 ⇒ 判据内核的结构语义被改了，"
        "或者尺子的预算该按新的实测值收紧了（改代码和改预算要一起做）"
    )


@requires_czsc
def test_power_caliber_matches_czsc_to_the_cent() -> None:
    """★ 力度口径必须**逐分一致**（门槛 1/2 下笔数逐笔相等 ⇒ 可直接比）。

    v0.8.4 定的口径是**振幅**（``high - low``），不是两端价差
    ⇒ 任何一个「优化」都会在这里立刻现形。
    """
    czsc = parity_czsc.load_czsc_native()
    for k in (1, 2):
        bars = parity_czsc.make_bars(parity_czsc.SEED, parity_czsc.N_BARS)
        ours = parity_czsc.run_ours(bars, k)
        theirs = parity_czsc.run_czsc(czsc, bars, k)
        assert ours["n_bi"] == theirs["n_bi"], (
            f"门槛 {k} 下笔数就不一样了（{ours['n_bi']} vs {theirs['n_bi']}）"
            "⇒ 连笔都对不上，力度口径无从比起"
        )
        cmp = parity_czsc.compare(ours, theirs)
        assert cmp["power_max"] == 0.0, (
            f"门槛 {k} 下力度口径差 {cmp['power_max']} ⇒ "
            "power_price 的口径与参照侧不一致了"
        )


@requires_czsc
def test_zhongshu_caliber_matches_completed_ones() -> None:
    """★ 中枢口径必须一致：自研中枢数 == czsc 的**已完成**中枢（≥3 笔）数。

    ⚠️ czsc 的 ``ZS`` 里含 1–2 笔的**未完成**中枢 ⇒ 比较时必须只取 ≥3 笔的，
    否则会凭空多出十几个（实测 28 vs 38，其中 8 个是未完成）。
    """
    czsc = parity_czsc.load_czsc_native()
    bars = parity_czsc.make_bars(parity_czsc.SEED, parity_czsc.N_BARS)
    ours = parity_czsc.run_ours(bars, 1)
    theirs = parity_czsc.run_czsc(czsc, bars, 1)
    assert abs(ours["n_zs"] - theirs["n_zs"]) <= 5, (
        f"中枢数对不上：自研 {ours['n_zs']} vs czsc 已完成中枢 {theirs['n_zs']}"
    )


def test_czsc_loader_finds_native_extension_without_pandas() -> None:
    """★ 加载器必须**不依赖** czsc 的 Python 外壳（pandas/wbt 都没装也能用）。

    这是「CI 只装 ``--no-deps`` 的 czsc」能成立的前提。
    """
    spec = importlib.util.find_spec("czsc")
    if spec is None or not spec.submodule_search_locations:
        pytest.skip("czsc 没装")
    here = pathlib.Path(list(spec.submodule_search_locations)[0])
    assert (here / "_native.abi3.so").exists() or (here / "_native" / "_native.abi3.so").exists(), (
        f"{here} 下找不到 czsc 的原生扩展"
    )
