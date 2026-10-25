#!/usr/bin/env python3
"""czsc × 自研 对账门禁 —— 判据内核与参照侧之间的「尺子」。

为什么需要它
------------
生产用的是**自研后端**（``emotion_cpt.structure``），机器上另有一份**参照侧**
（czsc 1.0.x 原生包）。两边的「笔 / 中枢」本该是同一件事的两套实现，
但 2026-10-25 实测发现：**``min_bi_len`` 门槛 >= 3 时两边的笔数能差 40%+**。

⇒ 没有这把尺子，后面所有结构改动都是**盲改**：改完只能靠「图看着对」来判断。

这个脚本做什么
--------------
用**固定随机种子的合成行情**（不连库 ⇒ CI 能跑）对同一批 K 线跑两条链，
输出三个数字：

    笔数差     自研笔数 - czsc 笔数
    中枢数差   自研中枢数 - czsc 中枢数
    力度口径差 逐笔 power_price 的最大绝对差（自研 vs czsc）

**差距本身不是 bug**（两套实现本就可以不同）⇒ 门禁的判据是
**差距不能无声变大**：预算写在上方，超预算就红 ⇒ 「结构语义悄悄变了」会当场被抓住。

用法
----
    python scripts/parity_czsc.py                     # 全部门槛
    python scripts/parity_czsc.py --min-bi-len 3 6     # 只看某几档
    python scripts/parity_czsc.py --json              # 机器可读

退出码：0 = 差距在预算内；1 = 超预算；2 = 环境不可用（czsc 不可用 ⇒ 不算通过也不算失败）

依赖
----
czsc **只用于对账**，不是本仓的运行时依赖 ⇒ 核心仍是零三方依赖。

装法（CI 与本机通用）::

    pip install --no-deps "czsc==1.0.1" pandas

- ``--no-deps``：czsc 声明的 scipy / polars / statsmodels / plotly / wbt … **全都不要**
  （脚本只用 Rust 扩展；构造 ``RawBar`` 只依赖标准库的 ``datetime``）
- ``pandas``：**需要** —— 读 czsc 笔的端点时间（``.dt`` 返回 pandas Timestamp）

脚本会自动降级：``import czsc`` 失败时**直接加载** ``czsc/_native.abi3.so``
（Rust 扩展本身零 Python 三方依赖；``importlib.util.find_spec`` 不执行
``czsc/__init__.py`` ⇒ 缺 wbt 也能找到它）。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

# ── 预算（差距上限）────────────────────────────────────────────────────
# 2026-10-25 实测基线（合成行情 6 轮 × 400 根）：
#   门槛 1/2：笔数差 +0（**逐笔相等**）· 中枢数差 -2 · 力度口径差 **0.0000**
#   门槛 3  ：笔数差 -485（自研少一半）· 中枢数差 -52 · 力度口径差 11.21
#   门槛 6  ：笔数差  +36（自研多两成）· 中枢数差  +19 · 力度口径差  9.59
# ⚠️ 门槛 >=3 的力度差**不是噪声**：按端点时间配对后仍差 9~11
#    ⇒ 连「同一笔」的两端都不同（自研顺延合并 vs czsc 不成笔）⇒ 真实语义差。
#
# ⚠️ **它是「当前差距的快照」，不是「理想值」**：门禁的判据是
# **差距不能无声变大**。改结构语义让差距**变小**时，请**同时把这里收紧**
# （并在 commit 里写明收了多少）⇒ 这样"收敛"才不会被悄悄丢掉。
BUDGET: dict[int, dict[str, int]] = {
    1: {"bi": 5, "zs": 5, "power": 1},
    2: {"bi": 5, "zs": 5, "power": 1},
    3: {"bi": 550, "zs": 60, "power": 15},
    6: {"bi": 60, "zs": 25, "power": 15},
}

SEED = 20261025
N_BARS = 400
ROUNDS = 6
SYMBOL = "PARITY"


# ── czsc 侧加载 ──────────────────────────────────────────────────────
def load_czsc_native():
    """加载 czsc 的 Rust 扩展。

    优先 ``import czsc``（装了完整依赖时）。
    退路：直接加载 ``czsc/_native.abi3.so`` —— Rust 扩展本身**不依赖任何 Python 三方库**，
    只有 ``czsc/__init__.py`` 那个纯 Python 外壳才要 pandas/wbt。
    """
    try:
        import czsc  # noqa: PLC0415

        return czsc
    except Exception:
        pass
    # find_spec **不执行** czsc/__init__.py ⇒ 纯 Python 外壳缺 pandas/wbt 也能找到 .so
    spec = importlib.util.find_spec("czsc")
    if spec is None or not spec.submodule_search_locations:
        raise ImportError("czsc 没装")
    here = pathlib.Path(list(spec.submodule_search_locations)[0])
    for cand in (here / "_native.abi3.so", here / "_native" / "_native.abi3.so"):
        if cand.exists():
            mod_spec = importlib.util.spec_from_file_location("_native", cand)
            mod = importlib.util.module_from_spec(mod_spec)
            mod_spec.loader.exec_module(mod)
            return mod
    raise ImportError("找不到 czsc 的原生扩展（czsc/_native*.so）")


# ── 合成行情 ──────────────────────────────────────────────────────────
@dataclass
class Bar:
    """满足 ``emotion_cpt.structure.types.BarLike`` 的最小 K 线。"""

    open: float
    high: float
    low: float
    close: float
    volume: float
    dt: datetime = field(default_factory=lambda: datetime(2026, 1, 1, tzinfo=UTC))

    @property
    def open_time(self) -> int:
        """Unix 毫秒（仓内约定：bar 起始时刻）。

        ``dt`` 按 czsc 的约定存 **tz-naive**（市场本地时间以 UTC 数值存储），
        这里显式按 UTC 解读 ⇒ 两边看到的是同一批时刻。
        """
        return int(self.dt.replace(tzinfo=UTC).timestamp() * 1000)

    @property
    def close_time(self) -> int:
        """Unix 毫秒（仓内约定：bar 结束时刻）。"""
        return self.open_time + 86_400_000

    @property
    def direction(self) -> int:
        """方向标记：+1 向上 / -1 向下 / 0 中性。"""
        return 1 if self.close >= self.open else -1


def make_bars(seed: int, n: int) -> list[Bar]:
    """生成 ``n`` 根确定性随机行情（带上下影线，够产生分型与包含关系）。"""
    rng = random.Random(seed)
    price = 100.0
    bars: list[Bar] = []
    base = datetime(2026, 1, 1)  # tz-naive：czsc 要求 naive
    for i in range(n):
        price = max(1.0, price + rng.gauss(0.0, 1.1))
        hi = price + abs(rng.gauss(0.0, 0.55))
        lo = max(0.5, price - abs(rng.gauss(0.0, 0.55)))
        op = lo + (hi - lo) * rng.random()
        cl = lo + (hi - lo) * rng.random()
        bars.append(
            Bar(
                open=round(op, 2),
                high=round(max(hi, op, cl), 2),
                low=round(min(lo, op, cl), 2),
                close=round(cl, 2),
                volume=round(1000 + rng.random() * 5000, 2),
                dt=base + timedelta(days=i),  # tz-naive（czsc 约定）
            )
        )
    return bars


# ── 自研侧 ───────────────────────────────────────────────────────────
def run_ours(bars: list[Bar], min_bi_len: int) -> dict:
    from emotion_cpt.structure.bi import build_bis
    from emotion_cpt.structure.contain import merge_contained_bars
    from emotion_cpt.structure.fractal import detect_fractals
    from emotion_cpt.structure.zhongshu import build_zhongshus

    merged = merge_contained_bars(bars)
    fractals = detect_fractals(merged)
    bis = build_bis(fractals, min_bi_len=min_bi_len, bars=merged)
    zss = build_zhongshus(bis)
    return {
        "n_merged": len(merged),
        "n_fractals": len(fractals),
        "n_bi": len(bis),
        "n_zs": len(zss),
        "bis": [
            {
                "start": b.start_time,
                "end": b.end_time,
                "high": b.high,
                "low": b.low,
                "power_price": b.power_price,
                "length": b.length,
            }
            for b in bis
        ],
    }


# ── czsc 侧 ──────────────────────────────────────────────────────────
def run_czsc(czsc, bars: list[Bar], min_bi_len: int) -> dict:
    raw = [
        czsc.RawBar(
            symbol=SYMBOL,
            dt=b.dt,
            freq=czsc.Freq.D,
            open=b.open,
            close=b.close,
            high=b.high,
            low=b.low,
            vol=b.volume,
            amount=b.volume * b.close,
            id=i,
        )
        for i, b in enumerate(bars)
    ]
    c = czsc.CZSC(raw, max_bi_num=len(raw), min_bi_len=min_bi_len)
    bis = list(c.bi_list)
    zss = list(c.zs_list)
    # ⚠️ **口径**：czsc 的 ZS 里有 1–2 笔的「未完成中枢」（`ZS::new(vec![bi])`），
    # 自研的中枢要求三笔重叠才成立 ⇒ 比较必须**只取 czsc 的已完成中枢**（≥3 笔），
    # 否则会凭空多出十几个「未完成」中枢（2026-10-25 实测：28 vs 38，其中 38 里有 8 个是未完成）。
    done_zs = [z for z in zss if len(z.bis) >= 3]
    return {
        "n_merged": len(c.bars_ubi),
        "n_bi": len(bis),
        "n_zs": len(done_zs),
        "n_zs_all": len(zss),
        "bis": [
            {
                # 自研的端点时间 = 分型**中间 bar**的起止（Unix 毫秒）
                # ⚠️ 用 ``.value``（纳秒墙钟）而不是 ``.timestamp()``：
                #    后者把 naive 时间戳按**宿主本地时区**解释 ⇒ 换台机器/换个 TZ
                #    就对不上 ⇒ 对账结果会飘。
                #    czsc 的约定是「本地时间即 UTC 数值」⇒ 与自研侧口径一致。
                "start": int(x.fx_a.dt.value // 10**6),
                "end": int(x.fx_b.dt.value // 10**6),
                "high": float(x.high),
                "low": float(x.low),
                "power_price": float(x.power_price),
                "length": int(x.length),
            }
            for x in bis
        ],
    }


# ── 比对 ─────────────────────────────────────────────────────────────
def compare(ours: dict, theirs: dict) -> dict:
    """比对：笔数差 / 中枢数差 / 力度口径差。

    ⚠️ **力度按「时间对齐」比，不是按序号** ——
    两边笔数相等时，第 k 笔**未必是同一笔**（端点选取规则不同）⇒ 按序号比会算出
    一堆噪声。按端点时间配对，配不上的不参与比较。
    """
    bi_diff = ours["n_bi"] - theirs["n_bi"]
    zs_diff = ours["n_zs"] - theirs["n_zs"]
    theirs_by_start = {b["start"]: b for b in theirs["bis"]}
    power_diffs = []
    n_paired = 0
    for a in ours["bis"]:
        b = theirs_by_start.get(a["start"])
        if b is None:
            continue
        n_paired += 1
        if a["power_price"] and b["power_price"]:
            power_diffs.append(abs(a["power_price"] - b["power_price"]))
    power_max = round(max(power_diffs), 4) if power_diffs else None
    return {
        "bi_diff": bi_diff,
        "zs_diff": zs_diff,
        "power_max": power_max,
        "n_paired": n_paired,
        "n_ours_bi": ours["n_bi"],
        "n_czsc_bi": theirs["n_bi"],
        "n_ours_zs": ours["n_zs"],
        "n_czsc_zs": theirs["n_zs"],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-bi-len", type=int, nargs="*", default=sorted(BUDGET))
    ap.add_argument("--rounds", type=int, default=ROUNDS)
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = ap.parse_args(argv)

    try:
        czsc = load_czsc_native()
    except Exception as exc:  # pragma: no cover - 环境缺依赖
        print(f"⚠️ czsc 不可用（{exc}）⇒ 本门禁无法执行（不算通过）")
        return 2

    results = []
    over_budget = []
    for k in args.min_bi_len:
        agg = {"bi": 0, "zs": 0, "power": 0.0, "power_rounds": 0}
        detail = []
        for r in range(args.rounds):
            bars = make_bars(SEED + r, N_BARS)
            ours = run_ours(bars, k)
            theirs = run_czsc(czsc, bars, k)
            cmp = compare(ours, theirs)
            agg["bi"] += cmp["bi_diff"]
            agg["zs"] += cmp["zs_diff"]
            if cmp["power_max"] is not None:
                agg["power"] = max(agg["power"], cmp["power_max"])
                agg["power_rounds"] += 1
            detail.append(cmp)
        budget = BUDGET.get(k, {"bi": 0, "zs": 0, "power": 0})
        item = {
            "min_bi_len": k,
            "bi_diff_sum": agg["bi"],
            "zs_diff_sum": agg["zs"],
            "power_max": round(agg["power"], 4),
            "power_compared_rounds": agg["power_rounds"],
            "budget": budget,
            "over": bool(
                abs(agg["bi"]) > budget["bi"]
                or abs(agg["zs"]) > budget["zs"]
                or agg["power"] > budget["power"]
            ),
            "rounds": detail,
        }
        results.append(item)
        if item["over"]:
            over_budget.append(item)

    if args.json:
        print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    else:
        print("=" * 88)
        print("czsc × 自研 对账（合成行情，固定种子 ⇒ 可复现）")
        print("=" * 88)
        for item in results:
            mark = "❌ 超预算" if item["over"] else "✅ 在预算内"
            pw = f"{item['power_max']:.4f}" if item["power_compared_rounds"] else "不比较(笔未对齐)"
            print(
                f"min_bi_len={item['min_bi_len']:>2}  "
                f"笔数差 {item['bi_diff_sum']:>+6} / 预算 {item['budget']['bi']:>4}  "
                f"中枢数差 {item['zs_diff_sum']:>+5} / 预算 {item['budget']['zs']:>3}  "
                f"力度口径差 {pw} / 预算 {item['budget']['power']}  {mark}"
            )
        print("-" * 88)
        print(f"{len(results)} 档门槛，{args.rounds} 轮 × {N_BARS} 根")
        print("中枢口径 = czsc 的**已完成**中枢（≥3 笔）；力度按**端点时间**配对后比较")
    return 1 if over_budget else 0


if __name__ == "__main__":
    raise SystemExit(main())
