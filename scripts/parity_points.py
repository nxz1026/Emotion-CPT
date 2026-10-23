#!/usr/bin/env python3
"""结构位→买卖参考位 的 parity 工具（两侧当前实现 vs 统一后的实现）。

背景：CPT `cpt/application/track_points.py` 与 emotion-core `algorithms/levels.py`
各写了一份**同一算式**（中枢下沿/向上笔低点取 min、÷ratio×1.02；上沿取 max、÷ratio×0.97），
但**取整位数不同**（CPT 2 位 / emotion 3 位）⇒ 同一支票两个系统可能印出不同的买点价。
2026-10-23 统一到 ``emotion_cpt.snapshot.points``。

用法::

    # 改之前：采黄金参考
    python scripts/parity_points.py --mode before --out /tmp/points_before.json
    # 改之后：采新实现
    python scripts/parity_points.py --mode after  --out /tmp/points_after.json
    # 比对
    python scripts/parity_points.py --compare /tmp/points_before.json /tmp/points_after.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

CPT_ROOT = "/home/ubuntu/DSH/Chan_Pattern_Trader"
EMO_ROOT = "/home/ubuntu/DSH/emotion-core"
OVERLAYS_FILE = "/tmp/points_overlays.json"

#: ratio 矩阵：None / 1.0 / 小数 / 大于 1 —— 覆盖 ratio 无效、恒等、缩放、放大四种分支
RATIOS = (None, 1.0, 0.8765, 1.5)


def load_overlays() -> dict[str, dict]:
    p = pathlib.Path(OVERLAYS_FILE)
    if not p.exists():
        raise SystemExit(f"缺 {OVERLAYS_FILE}，先跑 --dump-overlays")
    return json.loads(p.read_text(encoding="utf-8"))


def run_cpt(overlays: dict, ratio: float | None) -> dict:
    from cpt.application import track_points as tp

    bis, zs = overlays.get("bis") or [], overlays.get("zhongshus") or []
    out: dict = {"buy": None, "sell": None, "buy_reason": None, "sell_reason": None}
    if ratio is not None and ratio > 0:
        b = tp._buy_reference(bis, zs, ratio)
        s = tp._sell_reference(bis, zs, ratio)
        out["buy"] = b.get("price_level") if b else None
        out["sell"] = s.get("price_level") if s else None
        out["buy_reason"] = b.get("rationale") if b else None
        out["sell_reason"] = s.get("rationale") if s else None
    return out


def run_emotion(overlays: dict, ratio: float | None) -> dict:
    from emotion_core.algorithms import levels as lv

    buy, sell = lv._picks(overlays, ratio) if ratio is not None and ratio > 0 else (None, None)
    return {
        "buy": round(buy, 3) if buy is not None else None,
        "sell": round(sell, 3) if sell is not None else None,
        "buy_reason": None,
        "sell_reason": None,
    }


def run_shared(overlays: dict, ratio: float | None) -> dict:
    from emotion_cpt.snapshot.points import structure_picks

    buy, sell = structure_picks(overlays, ratio)
    return {
        "buy": round(buy, 2) if buy is not None else None,   # CPT 口径：2 位
        "sell": round(sell, 2) if sell is not None else None,
        "buy_reason": None,
        "sell_reason": None,
    }


def dump_overlays(out: pathlib.Path) -> None:
    """从线上看板抓真实 overlays（只读 GET）。"""
    import urllib.request

    payload: dict[str, dict] = {}
    for code in ("600519", "000016", "601811", "300750", "002594", "688111", "301718"):
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:8010/api/dashboard/a-share/snapshot?code={code}", timeout=25
            ) as r:
                data = json.loads(r.read())
            ov = data.get("overlays") or {}
            if ov:
                payload[code] = ov
        except Exception as exc:  # noqa: BLE001
            print(f"  {code} 取数失败: {exc}", file=sys.stderr)
    out.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(f"✅ 已抓 {len(payload)} 只票的 overlays → {out}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="结构位 parity 工具")
    ap.add_argument("--mode", choices=["before", "after"])
    ap.add_argument("--out", type=pathlib.Path)
    ap.add_argument("--compare", nargs=2, type=pathlib.Path)
    ap.add_argument("--dump-overlays", type=pathlib.Path)
    args = ap.parse_args(argv)

    if args.dump_overlays:
        dump_overlays(args.dump_overlays)
        return 0
    if args.compare:
        a = json.loads(args.compare[0].read_text(encoding="utf-8"))
        b = json.loads(args.compare[1].read_text(encoding="utf-8"))
        bad = [k for k in a if a[k] != b.get(k)]
        if bad:
            print(f"❌ {len(bad)} 处不一致:")
            for k in bad[:6]:
                print(f"   {k}\n     前={a[k]}\n     后={b.get(k)}")
            return 1
        print(f"✅ 完全一致（{len(a)} 组）")
        return 0
    if args.mode and args.out:
        sys.path.insert(0, CPT_ROOT)
        sys.path.insert(0, EMO_ROOT + "/src")
        overlays = load_overlays()
        result: dict[str, dict] = {}
        for code, ov in sorted(overlays.items()):
            for r in RATIOS:
                key = f"{code}@ratio={r}"
                if args.mode == "before":
                    result[key] = {"cpt": run_cpt(ov, r), "emotion": run_emotion(ov, r)}
                else:
                    result[key] = {"cpt": run_cpt(ov, r), "emotion": run_emotion(ov, r),
                                   "shared": run_shared(ov, r)}
        args.out.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=1),
                            encoding="utf-8")
        print(f"✅ {args.mode} → {args.out}（{len(result)} 组）")
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
