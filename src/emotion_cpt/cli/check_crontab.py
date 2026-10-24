"""crontab **双向**对账门禁。

为什么必须双向：cron 的失败是**静默**的 ——
路径不存在 ⇒ cron 直接跳过，不报错；脚本丢执行位 ⇒ Permission denied，也不报错。
（本门禁是那几条「只活在线上、不在任何仓里」的作业的 catcher。）

查三件事：

1. **双向对账**：仓内真相源 ↔ 线上 crontab，任一方向多一条/少一条都红；
2. **每条作业引用的脚本都存在且有执行位**（含仓外的 ``/home/ubuntu/bin/*.sh``）——
   这是「重建环境后作业静默消失」的 catcher；
3. **归属提示**：哪些作业的命令指向**别的仓**（外部脚本），让 review 时知道边界在哪。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_CRONTAB = Path(__file__).resolve().parents[1] / "deploy" / "cron" / "crontab"

#: 本仓自己管的路径前缀（仓内脚本）
_OWN_PREFIXES = ("/home/ubuntu/DSH/Emotion-CPT/", "/home/ubuntu/DSH/Chan_Pattern_Trader/")


def _jobs(text: str) -> dict[str, str]:
    """从 crontab 文本抽 ``{整行: 调度行}``。

    ⚠️ **key 必须是整行，不能是命令**（2026-10-24 实测踩过）：
    两条不同时间、**同一条命令**的作业（``factor-carry-forward.sh`` 的 09:45 与 11:30）
    按命令做 key 会被字典**合并成一条** ⇒ 门禁视野里少一条作业 ⇒
    「增删一条作业」可能完全不报警。**这正是「断言了但什么都没断言」那一类。**
    """
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 5)
        if len(parts) < 6:
            continue
        out[line] = " ".join(parts[:5])
    return out


def _live_crontab() -> str:
    try:
        return subprocess.run(  # noqa: S603 - 固定命令
            ["crontab", "-l"], capture_output=True, text=True, timeout=20, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"⚠️ 读不到线上 crontab：{exc}", file=sys.stderr)
        return ""


def _script_of(command: str) -> str | None:
    """从命令里取出被执行的脚本路径（取第一个像路径的 token）。"""
    for token in command.split():
        if token.startswith("/") and ("/" in token[1:]) and not token.startswith("/>"):
            if re.search(r"\.(sh|py)$", token):
                return token
    return None


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
    repo_jobs = _jobs(repo_text)

    # ── ① 每条作业引用的脚本：存在 + 执行位 ──
    scripts: list[Path] = []
    external: list[str] = []
    for line in repo_jobs:
        command = line
        script = _script_of(command)
        if script is None:
            continue
        path = Path(script)
        scripts.append(path)
        if not script.startswith(_OWN_PREFIXES):
            external.append(script)
        if not path.exists():
            issues.append(f"作业引用的脚本不存在：{script}（cron 会静默跳过）")
    for bad in _exec_bits(scripts):
        issues.append(f"脚本缺执行位（cron 不经过 shell ⇒ Permission denied 且静默）：{bad}")

    # ── ② 双向对账 ──
    if not args.skip_live:
        live_jobs = _jobs(_live_crontab())
        only_repo = sorted(set(repo_jobs) - set(live_jobs))
        only_live = sorted(set(live_jobs) - set(repo_jobs))
        for line in only_repo:
            issues.append(f"仓内有、线上没有：{line}")
        for line in only_live:
            issues.append(f"线上有、仓内没有（会静默消失）：{line}")

    if issues:
        print(f"❌ crontab 对账失败（{len(issues)} 项）：", file=sys.stderr)
        for issue in issues:
            print(f"  {issue}", file=sys.stderr)
        return 1

    print(
        f"✅ crontab 一致（仓内 {len(repo_jobs)} 条；"
        f"其中 {len(external)} 条指向外部仓的脚本，已登记并检查了存在性与执行位）"
    )
    for script in sorted(set(external)):
        print(f"   外部归属：{script}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
