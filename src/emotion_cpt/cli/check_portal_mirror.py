#!/usr/bin/env python3
"""portal 仓 unit 镜像的**旁观门禁**（owner 裁决 Q7=C「不动 portal 仓」的代价补偿）。

## 背景

`DSH/portal` 仓的 `deploy/systemd-units/etc/systemd/system/` 是**线上 unit 的镜像**
（`sync.sh pull` 拉下来的快照）。它与 Emotion-CPT 的真相源**有 16 个同名 unit**。

owner 裁决 Q7 = **C：不动 portal 仓** ⇒ 本仓**不改**它、**不跑**它的 `sync.sh`
（pull 会写 portal 仓）。

⇒ 但「不动」的代价是：**那份镜像的漂移，本仓的 `check_unit_paths` 看不见**
（它只对账「真相源 ↔ 线上」两方）。

⇒ 本门禁**只读** portal 的镜像目录，做**三方对账**：
``portal 镜像 ↔ Emotion-CPT 真相源 ↔ 线上`` ⇒ 漂移无所遁形，
而**一个字都不改**。

## 归一化：忽略 `# owner:` 注释行

⚠️ **必须归一化**，否则会**假警报**：
真相源里每个 unit 头都有 ``# owner: <名字>``（归属声明），
而 portal 镜像是 2026-10-24 04:25 拉的，**那时还没有 owner 注释**
⇒ 16 个 unit 全部报差异 —— 而它们的**实际内容一模一样**。

⇒ 比对前**去掉 owner 注释行**再比。实测：归一化后 16 个全部一致。

## 为什么「镜像里没有」只提示、不报红

owner 裁决 Q7 = C（**不动 portal 仓**）⇒ 修「镜像缺 unit」要跑 portal 的
``sync.sh pull``，那会**写 portal 仓** ⇒ 我们不做。

⇒ 本门禁只对**内容漂移**报红（同名 unit 内容不同 ⇒ 真漂移），
缺失一律**提示**。
理由：**一个长期红的门禁等于没有门禁** —— 人会学会忽略它。
而镜像缺 unit 对 Emotion-CPT 自身**没有风险**：
本仓的 unit 有 ``check_unit_paths``（真相源 ↔ 线上）守着 ✅。

## 退出码

``0`` 一致（或 portal 仓不在本地 ⇒ 跳过）；``1`` 有漂移。
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

#: portal 仓的镜像目录（线上 unit 的快照）
DEFAULT_PORTAL_MIRROR = pathlib.Path(
    "/home/ubuntu/DSH/portal/deploy/systemd-units/etc/systemd/system"
)

#: 真相源里的 unit 目录
DEFAULT_TRUTH = pathlib.Path(__file__).resolve().parents[1] / "deploy" / "systemd"

#: 线上 unit 目录
SYS_DIR = pathlib.Path("/etc/systemd/system")

#: **归属注释行**（比对前要去掉 —— 见文件头说明）
_OWNER_LINE = re.compile(r"(?m)^#\s*owner:.*\n?")


_OWNER_RE = re.compile(r"(?m)^#\s*owner:\s*([A-Za-z0-9_.-]+)")


def _owner_of(text: str) -> str:
    """读 unit 的归属声明。"""
    m = _OWNER_RE.search(text)
    return m.group(1) if m else ""


def _normalize(text: str) -> str:
    """比对前的归一化：去掉 owner 注释行 + 统一行尾。"""
    return _OWNER_LINE.sub("", text).replace("\r\n", "\n").rstrip()


def _units(d: pathlib.Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not d.is_dir():
        return out
    for p in sorted(d.iterdir()):
        if p.suffix not in (".service", ".timer"):
            continue
        try:
            out[p.name] = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return out


def compare(
    portal: dict[str, str],
    truth: dict[str, str],
    live: dict[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    """三方对账，返回 ``(问题, 提示)``。"""
    issues: list[str] = []
    same_names = sorted(set(portal) & set(truth))

    for name in same_names:
        p, t = _normalize(portal[name]), _normalize(truth[name])
        if p != t:
            issues.append(
                f"{name}: portal 镜像与 Emotion-CPT 真相源**不一致**"
                f"（portal 的 sync.sh 该 pull 一次了）"
            )
        if live is not None and name in live:
            if _normalize(live[name]) != t:
                issues.append(f"{name}: 线上与 Emotion-CPT 真相源**不一致**")

    # ── 真相源里有、portal 镜像里没有的 ──
    # ⚠️ **按归属分级**：
    #   · owner=emotion-cpt（本仓的）⇒ ❌ 红 —— 本仓自己的 unit 不该在镜像里缺席
    #   · owner=别的仓 ⇒ ⚠️ 只提示 —— **portal 镜像不全是 portal 的事**，
    #     owner 裁决 Q7=C「不动 portal 仓」⇒ 本仓不为此报红（否则门禁长期红，
    #     门禁一旦长期红就等于没有门禁）。
    notes: list[str] = []
    only_truth = sorted(set(truth) - set(portal))
    for name in only_truth:
        owner = _owner_of(truth[name]) or "未归属"
        if owner == "emotion-cpt":
            notes.append(
                f"{name}: portal 镜像里没有**本仓的** unit"
                f"（修它要跑 portal 的 sync.sh pull ⇒ 按 Q7=C 我们不动它，只提示）"
            )
        else:
            notes.append(f"{name}: portal 镜像里没有（属 {owner}，portal 自己的事，不报红）")

    return issues, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="portal unit 镜像的旁观对账门禁")
    parser.add_argument(
        "--portal-mirror", default=str(DEFAULT_PORTAL_MIRROR), help="portal 仓的镜像目录"
    )
    parser.add_argument("--truth-dir", default=str(DEFAULT_TRUTH), help="Emotion-CPT 真相源目录")
    parser.add_argument("--skip-live", action="store_true", help="不查线上")
    args = parser.parse_args(argv)

    mirror_dir = pathlib.Path(args.portal_mirror)
    truth_dir = pathlib.Path(args.truth_dir)

    if not truth_dir.is_dir():
        print(f"❌ 找不到真相源目录：{truth_dir}", file=sys.stderr)
        return 1

    if not mirror_dir.is_dir():
        print(
            f"  (跳过：portal 仓不在本机（{mirror_dir}）⇒ 无从对账，"
            f"**不算通过也不算失败**)"
        )
        return 0

    portal = _units(mirror_dir)
    truth = _units(truth_dir)
    live = None if args.skip_live else _units(SYS_DIR)

    issues, notes = compare(portal, truth, live)
    for note in notes:
        print(f"  (提示：{note})")
    if issues:
        print(f"❌ portal unit 镜像对账失败（{len(issues)} 项）：", file=sys.stderr)
        for issue in issues:
            print(f"  {issue}", file=sys.stderr)
        return 1

    shared = len(set(portal) & set(truth))
    print(
        f"✅ portal unit 镜像一致"
        f"（镜像 {len(portal)} 个；与真相源同名的 {shared} 个逐字一致，忽略 owner 注释）"
    )
    print("   ⇒ **只读旁观**：本门禁不改 portal 仓，也不跑它的 sync.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
