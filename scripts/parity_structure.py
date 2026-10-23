#!/usr/bin/env python3
"""结构计算 parity 工具：同一批真实 K 线 ⇒ 两套实现必须给出**逐字段一致**的结果。

用途
----
搬迁 ``cpt/domain`` → ``emotion_cpt/structure`` 时，证明「逐字搬迁没有改变任何判据」。
判据 = **同输入同输出**：两套实现读**同一份** bars JSON，跑同一条链，逐字段比对。

用法::

    # ① 从真库导出真实 K 线（一次性，两边共用同一份文件）
    python scripts/parity_structure.py --dump-bars /tmp/bars.json

    # ② 迁移前：用原实现跑，存黄金参考
    python scripts/parity_structure.py --impl cpt         --bars /tmp/bars.json --out /tmp/golden.json

    # ③ 迁移后：用新实现跑
    python scripts/parity_structure.py --impl emotion_cpt --bars /tmp/bars.json --out /tmp/new.json

    # ④ 比对
    python scripts/parity_structure.py --compare /tmp/golden.json /tmp/new.json
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone

CST = timezone(timedelta(hours=8))


# ────────────────────────── ① 导出真实 K 线 ──────────────────────────
def dump_bars(out: pathlib.Path, codes: list[str], limit: int) -> None:
    from emotion_cpt.db.connection import connect

    conn = connect()
    try:
        with conn.cursor() as cur:
            payload: dict[str, list] = {}
            for code in codes:
                cur.execute(
                    "SELECT date, open, high, low, close FROM public.daily_bar "
                    "WHERE code = %s ORDER BY date DESC LIMIT %s",
                    (code, limit),
                )
                rows = cur.fetchall()
                payload[code] = [
                    {"date": str(r[0]), "open": float(r[1]), "high": float(r[2]),
                     "low": float(r[3]), "close": float(r[4])}
                    for r in reversed(rows)
                ]
    finally:
        conn.close()
    out.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    total = sum(len(v) for v in payload.values())
    print(f"✅ 已导出 {total} 根 K 线（{len(payload)} 只）→ {out}")


# ────────────────────────── ② 跑结构链 ──────────────────────────
def _asdict(obj) -> dict:
    """领域对象 ⇒ dict。

    ⚠️ 这些是 **frozen + slots** 的 dataclass，**没有 __dict__** ⇒ 必须用 asdict。
    """
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    return dict(getattr(obj, "__dict__", {}))


def run_chain(impl: str, bars: list[dict], min_bi_len: int | None) -> dict:
    if impl == "cpt":
        from cpt.domain.bi import build_bis
        from cpt.domain.fractal import detect_fractals
        from cpt.domain.models import make_canonical_bar
        from cpt.domain.recursion import map_trend_types
        from cpt.domain.trend_type import classify_trend
        from cpt.domain.zhongshu import build_zhongshus
    elif impl == "emotion_cpt":
        from emotion_cpt.structure.bi import build_bis
        from emotion_cpt.structure.fractal import detect_fractals
        from emotion_cpt.structure.models import make_canonical_bar
        from emotion_cpt.structure.recursion import map_trend_types
        from emotion_cpt.structure.trend_type import classify_trend
        from emotion_cpt.structure.zhongshu import build_zhongshus
    else:
        raise SystemExit(f"未知实现：{impl}")

    canonical = []
    for i, b in enumerate(bars):
        d = datetime.fromisoformat(b["date"]).replace(tzinfo=CST)
        open_ms = int(d.replace(hour=9, minute=30).timestamp() * 1000)
        close_ms = int(d.replace(hour=15, minute=0).timestamp() * 1000)
        canonical.append(
            make_canonical_bar(open_ms, b["open"], b["high"], b["low"], b["close"], close_ms)
        )

    fractals = detect_fractals(canonical, level=0)
    bis = build_bis(fractals, level=0, min_bi_len=min_bi_len)
    zhongshus = build_zhongshus(bis, level=0)
    trends = classify_trend(bis, zhongshus)
    elements = map_trend_types(trends, 1)

    return {
        "n_bars": len(canonical),
        "fractals": [_asdict(f) for f in fractals],
        "bis": [_asdict(b) for b in bis],
        "zhongshus": [_asdict(z) for z in zhongshus],
        "trends": [_asdict(t) for t in trends],
        "elements": [_asdict(e) for e in elements],
    }


def _jsonable(obj):
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def run(impl: str, bars_file: pathlib.Path, out: pathlib.Path, min_bi_len: int | None) -> None:
    payload = json.loads(bars_file.read_text(encoding="utf-8"))
    result: dict[str, dict] = {}
    for code, bars in sorted(payload.items()):
        result[code] = _jsonable(run_chain(impl, bars, min_bi_len))
    out.write_text(
        json.dumps({"impl": impl, "min_bi_len": min_bi_len, "result": result},
                   ensure_ascii=False, sort_keys=True, indent=1),
        encoding="utf-8",
    )
    summary = {c: (len(r["fractals"]), len(r["bis"]), len(r["zhongshus"]), len(r["trends"]))
               for c, r in result.items()}
    print(f"✅ {impl}: {out}")
    print(f"   (分型,笔,中枢,走势) {summary}")


# ────────────────────────── ③ 比对 ──────────────────────────
def compare(a: pathlib.Path, b: pathlib.Path) -> int:
    da = json.loads(a.read_text(encoding="utf-8"))
    db = json.loads(b.read_text(encoding="utf-8"))
    if da.get("min_bi_len") != db.get("min_bi_len"):
        print(f"❌ 门槛不同：{da.get('min_bi_len')} vs {db.get('min_bi_len')}")
        return 1
    ra, rb = da["result"], db["result"]
    if set(ra) != set(rb):
        print(f"❌ 股票集合不同：{set(ra) ^ set(rb)}")
        return 1
    diffs: list[str] = []
    for code in sorted(ra):
        for key in ("n_bars", "fractals", "bis", "zhongshus", "trends", "elements"):
            if ra[code][key] != rb[code][key]:
                diffs.append(f"{code}.{key}")
                la, lb = ra[code][key], rb[code][key]
                if isinstance(la, list) and isinstance(lb, list):
                    diffs.append(f"    长度 {len(la)} vs {len(lb)}")
                    for i, (x, y) in enumerate(zip(la, lb)):
                        if x != y:
                            diffs.append(f"    [{i}] {x}")
                            diffs.append(f"    [{i}] {y}")
                            break
                else:
                    diffs.append(f"    {la!r} vs {lb!r}")
    if diffs:
        print("❌ parity 不一致：")
        for d in diffs:
            print(f"   {d}")
        return 1
    print(f"✅ parity 完全一致（{len(ra)} 只股票 × 6 类输出，门槛 min_bi_len={da.get('min_bi_len')}）")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="结构计算 parity 工具")
    ap.add_argument("--impl", choices=["cpt", "emotion_cpt"])
    ap.add_argument("--dump-bars", type=pathlib.Path)
    ap.add_argument("--bars", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path)
    ap.add_argument("--compare", nargs=2, type=pathlib.Path)
    ap.add_argument("--codes", default="600519,000016,601811,300750,002594")
    ap.add_argument("--limit", type=int, default=250)
    ap.add_argument("--min-bi-len", type=int, default=None)
    args = ap.parse_args(argv)

    if args.compare:
        return compare(*args.compare)
    if args.dump_bars:
        dump_bars(args.dump_bars, args.codes.split(","), args.limit)
        return 0
    if args.impl and args.bars and args.out:
        run(args.impl, args.bars, args.out, args.min_bi_len)
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
