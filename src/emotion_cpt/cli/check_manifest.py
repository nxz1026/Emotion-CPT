"""表 manifest 门禁：本仓 manifest ↔ 真库 ``pg_tables``。

真值来源是**真库**，不是文档。2026-10-23 实测真值：
52 张表 = emotion-core 37 + CPT 14 + 反契约表 1。

只读：只跑 ``SELECT``，不建表、不改表。
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Any

from emotion_cpt.contracts.tables import TABLES


def fetch_live_tables(conn: Any) -> set[str]:
    """从库里取全部 public 表名（只读）。"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r'"
        )
        return {row[0] for row in cur.fetchall()}


def compare(manifest: tuple[Any, ...], live: set[str]) -> list[str]:
    """比对，返回人类可读的差异描述。"""
    declared = {spec.name for spec in manifest}
    missing = sorted(declared - live)      # 登记了但库里没有
    extra = sorted(live - declared)        # 库里有但没登记
    out: list[str] = []
    if missing:
        out.append(f"manifest 登记了但库里没有（{len(missing)}）：{missing}")
    if extra:
        out.append(f"库里有但 manifest 没登记（{len(extra)}）：{extra}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="表 manifest 门禁（只读）")
    parser.add_argument("--dbconfig", default=None, help="凭据文件路径（默认 ~/.dbconfig）")
    args = parser.parse_args(argv)

    from emotion_cpt.db.connection import DbConfigError, connect

    try:
        conn = connect(pathlib.Path(args.dbconfig) if args.dbconfig else None)
    except DbConfigError as exc:
        print(f"⚠️ 无法连库，跳过（{exc}）", file=sys.stderr)
        return 0  # 没有凭据不算漂移，但要显式说明
    try:
        live = fetch_live_tables(conn)
    finally:
        conn.close()

    issues = compare(TABLES, live)
    if issues:
        print(f"❌ manifest 与真库不一致：", file=sys.stderr)
        for issue in issues:
            print(f"  {issue}", file=sys.stderr)
        return 1
    print(f"✅ manifest 与真库一致（{len(live)} 张表）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
