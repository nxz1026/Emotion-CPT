"""crontab **双向**对账门禁。

为什么必须双向：cron 的失败是**静默**的 ——
路径不存在 ⇒ cron 直接跳过，不报错；脚本丢执行位 ⇒ Permission denied，也不报错。
（本门禁是那几条「只活在线上、不在任何仓里」的作业的 catcher。）

查三件事：

1. **双向对账**：仓内真相源 ↔ 线上 crontab，任一方向多一条/少一条都红；
2. **每条作业引用的脚本都存在且有执行位**（含仓外的 ``/home/ubuntu/bin/*.sh``）——
   这是「重建环境后作业静默消失」的 catcher；
3. **归属分组**：每条作业归哪个仓，由真相源里的 ``# owner:`` 分组注释声明
   ⇒ 报红时直接说「这条归谁」，review 时知道边界在哪。

⚠️ 解析**只有一份实现**：`emotion_cpt.deploy.cron_spec`（P7 建的）。
本门禁曾自己写了一份 `_jobs()` ⇒ 两份解析实现 = 两份会漂的副本
（2026-10-24 已合并）。

⚠️ 与 `scripts/install_crontab.sh --check` **口径必须一致**：
两边都按**作业行**比对、忽略注释 ⇒ 不会出现「门禁绿、那个脚本报红」。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from emotion_cpt.deploy.cron_spec import parse_crontab

DEFAULT_CRONTAB = Path(__file__).resolve().parents[1] / "deploy" / "cron" / "crontab"


def _live_crontab() -> str:
    try:
        return subprocess.run(  # noqa: S603 - 固定命令
            ["crontab", "-l"], capture_output=True, text=True, timeout=20, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"⚠️ 读不到线上 crontab：{exc}", file=sys.stderr)
        return ""


def _exec_bits(paths: list[Path]) -> list[str]:
    bad: list[str] = []
    for path in paths:
        if path.exists() and not (path.stat().st_mode & 0o111):
            bad.append(str(path))
    return bad


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="crontab 双向对账门禁")
    parser.add_argument("--crontab-file", default=str(DEFAULT_CRONTAB), help="仓内 crontab 真相源")
    parser.add_argument("--skip-live", action="store_true", help="只做仓内自检（CI 用）")
    args = parser.parse_args(argv)

    repo_crontab = Path(args.crontab_file)

    issues: list[str] = []

    if not repo_crontab.exists():
        print(f"❌ 仓内 crontab 真相源不存在：{repo_crontab}", file=sys.stderr)
        return 1

    repo_text = repo_crontab.read_text(encoding="utf-8")
    repo_jobs = parse_crontab(repo_text)
    by_line = {job.line: job for job in repo_jobs}

    # ── ① 每条作业引用的脚本：存在 + 执行位 ──
    scripts: list[Path] = []
    for job in repo_jobs:
        if not job.script or not job.script.startswith("/"):
            continue
        path = Path(job.script)
        scripts.append(path)
        if not path.exists():
            issues.append(
                f"[{job.owner or '未归属'}] 作业引用的脚本不存在：{job.script}"
                f"（cron 会静默跳过）"
            )
    for bad in _exec_bits(scripts):
        issues.append(f"脚本缺执行位（cron 不经过 shell ⇒ Permission denied 且静默）：{bad}")

    # ── ② 双向对账 ──
    if not args.skip_live:
        live_jobs = parse_crontab(_live_crontab())
        live_lines = {job.line for job in live_jobs}
        repo_lines = set(by_line)
        for line in sorted(repo_lines - live_lines):
            owner = by_line[line].owner or "未归属"
            issues.append(f"[{owner}] 仓内有、线上没有：{line}")
        for line in sorted(live_lines - repo_lines):
            issues.append(f"[线上独有] 线上有、仓内没有（会静默消失）：{line}")

    # ── ③ 未声明归属的作业 ⇒ 单独点名（归属必须显式，不能靠猜）──
    for job in repo_jobs:
        if not job.owner:
            issues.append(
                f"[未归属] 作业没有声明 owner"
                f"（真相源里加 ``# owner:`` 分组注释）：{job.line}"
            )

    if issues:
        print(f"❌ crontab 对账失败（{len(issues)} 项）：", file=sys.stderr)
        for issue in issues:
            print(f"  {issue}", file=sys.stderr)
        return 1

    # ── 成功：按归属分组报数 ──
    groups: dict[str, int] = {}
    for job in repo_jobs:
        groups[job.owner or "未归属"] = groups.get(job.owner or "未归属", 0) + 1
    detail = "、".join(f"{owner} {n} 条" for owner, n in sorted(groups.items()))
    print(f"✅ crontab 一致（仓内 {len(repo_jobs)} 条：{detail}）")
    print("   ⇒ 真相源宿主 = Emotion-CPT；**变更责任在 owner 那一栏**")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
