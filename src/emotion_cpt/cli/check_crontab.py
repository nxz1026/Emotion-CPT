"""crontab **双向**对账门禁。

为什么必须双向：cron 的失败是**静默**的 ——
路径不存在 ⇒ cron 直接跳过，不报错；脚本丢执行位 ⇒ Permission denied，也不报错。
（本仓的门禁是那 4 条「只活在线上」的作业的 catcher。）
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_CRONTAB = Path("deploy/cron/crontab")


def _jobs(text: str) -> dict[str, str]:
    """从 crontab 文本抽 ``{命令: 调度行}``。"""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 5)
        if len(parts) < 6:
            continue
        out[" ".join(parts[5:])] = " ".join(parts[:5])
    return out


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
        print(f"⚠️ 仓内 crontab 不存在：{repo_crontab}（本仓尚未接管部署真相源）")
        return 0

    repo_jobs = _jobs(repo_crontab.read_text(encoding="utf-8"))
    scripts = sorted(repo_crontab.parent.glob("*.sh"))
    bad_bits = _exec_bits(scripts)
    if bad_bits:
        issues.append(f"脚本缺执行位（cron 不经过 shell ⇒ Permission denied 且静默）：{bad_bits}")

    if not args.skip_live:
        live_jobs = _jobs(_live_crontab())
        only_repo = sorted(set(repo_jobs) - set(live_jobs))
        only_live = sorted(set(live_jobs) - set(repo_jobs))
        if only_repo:
            issues.append(f"仓内有、线上没有（{len(only_repo)}）：{only_repo}")
        if only_live:
            issues.append(f"线上有、仓内没有（{len(only_live)}）：{only_live}")

    if issues:
        print(f"❌ crontab 对账失败（{len(issues)} 项）：", file=sys.stderr)
        for issue in issues:
            print(f"  {issue}", file=sys.stderr)
        return 1
    print(f"✅ crontab 一致（仓内 {len(repo_jobs)} 条）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
