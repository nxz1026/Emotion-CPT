"""systemd unit 路径门禁：unit 里写死的路径必须存在。

背景：合并/搬迁时 unit 里的写死路径是最容易漏改、且**失败静默**的地方
（cron 不经过 shell，systemd 则是路径不存在直接启动失败但可能没人盯着）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

#: 匹配 unit 文件里的绝对路径（/home/... 形态）
_PATH_RE = re.compile(r"(?<![\w/])(/home/[A-Za-z0-9_./-]+)")


def extract_paths(text: str) -> set[str]:
    out: set[str] = set()
    for raw in _PATH_RE.findall(text):
        path = raw.rstrip('"\'.,')
        # 去掉明显的文件参数（如 .py 后缀保留；目录保留）
        out.add(path)
    return out


def check_units(unit_dir: Path) -> list[str]:
    issues: list[str] = []
    if not unit_dir.exists():
        return [f"unit 目录不存在：{unit_dir}"]
    for unit in sorted(unit_dir.glob("*.service")) + sorted(unit_dir.glob("*.timer")):
        for path in extract_paths(unit.read_text(encoding="utf-8", errors="ignore")):
            if path.endswith((".py", ".sh", ".env", ".conf")):
                continue
            if not Path(path).exists():
                issues.append(f"{unit.name}: 路径不存在 {path}")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="systemd unit 路径门禁")
    parser.add_argument("--unit-dir", default="deploy/systemd", help="unit 目录")
    args = parser.parse_args(argv)

    issues = check_units(Path(args.unit_dir))
    if issues:
        print(f"❌ unit 路径问题（{len(issues)} 项）：", file=sys.stderr)
        for issue in issues:
            print(f"  {issue}", file=sys.stderr)
        return 1
    print("✅ unit 路径全部存在")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
