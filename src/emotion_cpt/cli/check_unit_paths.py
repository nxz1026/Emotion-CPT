"""systemd unit 门禁：**双向**对账 + 路径存在性 + 执行位。

为什么要有
----------
1. **双向对账**：仓内 ``deploy/systemd/`` 是 Emotion-CPT 管的 unit 的**唯一真相源**；
   线上多一个/少一个 ⇒ 有人在仓外改了，或有人漏装了。
2. **路径存在性**：unit 里的 ``WorkingDirectory`` / ``ExecStart`` 指向的路径必须存在 ——
   路径错 ⇒ systemd 启动失败，但**可能没人盯着**。
3. **执行位**：被 ``ExecStart`` 直接调用的脚本必须有执行位。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

#: unit 真相源：**包内**（随包分发）。用包路径而不是相对路径，
#: 这样从任何 cwd 跑都是同一份，且与 emotion-core 读到的是同一份。
DEFAULT_UNIT_DIR = Path(__file__).resolve().parents[1] / "deploy" / "systemd"

#: 线上 unit 目录
SYS_DIR = Path("/etc/systemd/system")

#: Emotion-CPT 管的 unit 前缀（**不吞并**别的项目的单元）
_MANAGED = (
    "cpt-",
    "emotion-core-",
    "emotion-cpt-",
    "emotion-intraday",
    "emotion-lab",
)

#: 从 unit 里抽路径
_WORKING_DIR = re.compile(r"^WorkingDirectory=(\S+)", re.M)
_EXEC_START = re.compile(r"^ExecStart=(\S+)", re.M)
_ENV_FILE = re.compile(r"^EnvironmentFile=-?(\S+)", re.M)


def _managed(name: str) -> bool:
    return name.startswith(_MANAGED)


def _live_units() -> dict[str, str]:
    """线上被管理的 unit：``{名字: 内容}``。"""
    out: dict[str, str] = {}
    if not SYS_DIR.is_dir():
        return out
    for path in sorted(SYS_DIR.iterdir()):
        if path.suffix not in (".service", ".timer"):
            continue
        if not _managed(path.name):
            continue
        try:
            out[path.name] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="systemd unit 双向对账门禁")
    parser.add_argument("--unit-dir", default=str(DEFAULT_UNIT_DIR), help="仓内 unit 真相源")
    parser.add_argument("--skip-live", action="store_true", help="只做仓内自检（CI 用）")
    args = parser.parse_args(argv)

    unit_dir = Path(args.unit_dir)
    issues: list[str] = []

    if not unit_dir.is_dir():
        print(f"❌ 仓内 unit 目录不存在：{unit_dir}", file=sys.stderr)
        return 1

    repo_units: dict[str, str] = {}
    for path in sorted(unit_dir.iterdir()):
        if path.suffix not in (".service", ".timer"):
            continue
        repo_units[path.name] = path.read_text(encoding="utf-8", errors="replace")

    if not repo_units:
        print(f"❌ 仓内 unit 目录里没有 unit：{unit_dir}", file=sys.stderr)
        return 1

    # ── ① 路径存在性 + 执行位 ──
    for name, text in sorted(repo_units.items()):
        for raw in _WORKING_DIR.findall(text):
            if not Path(raw).is_dir():
                issues.append(f"{name}: WorkingDirectory 不存在 {raw}")
        for raw in _EXEC_START.findall(text):
            if raw.startswith("/") and re.search(r"\.(sh|py)$", raw):
                p = Path(raw)
                if not p.exists():
                    issues.append(f"{name}: ExecStart 指向的文件不存在 {raw}")
                elif not (p.stat().st_mode & 0o111):
                    issues.append(f"{name}: ExecStart 指向的文件缺执行位 {raw}")
        for raw in _ENV_FILE.findall(text):
            # EnvironmentFile 是**外部**的凭据文件（不入仓）⇒ 只提示缺失
            if not Path(raw).exists():
                issues.append(f"{name}: EnvironmentFile 不存在 {raw}")

    # ── ② 双向对账 ──
    if not args.skip_live:
        live = _live_units()
        only_repo = sorted(set(repo_units) - set(live))
        only_live = sorted(set(live) - set(repo_units))
        for name in only_repo:
            issues.append(f"仓内有、线上没有：{name}")
        for name in only_live:
            issues.append(f"线上有、仓内没有（真相源漏了它）：{name}")
        for name in sorted(set(repo_units) & set(live)):
            if repo_units[name] != live[name]:
                issues.append(f"{name}: 仓内与线上内容不一致")

    if issues:
        print(f"❌ systemd unit 对账失败（{len(issues)} 项）：", file=sys.stderr)
        for issue in issues:
            print(f"  {issue}", file=sys.stderr)
        return 1
    print(f"✅ systemd unit 一致（{len(repo_units)} 个，路径存在、执行位、双向对账全过）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
