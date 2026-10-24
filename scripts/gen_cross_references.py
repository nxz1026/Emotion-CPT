#!/usr/bin/env python3
"""生成 ``docs/CROSS-REFERENCES.md`` —— 契约 ↔ 上游实现的交叉引用。

## 为什么用生成器而不是手写文档

手写的交叉引用**一定会烂**：上游挪个文件、契约加个模块，文档就变成骗人的东西，
而**没有任何东西会报警**。⇒ 交叉引用必须**可重算**，且重算时**校验路径真的存在**。

⇒ 路径不存在 ⇒ **生成失败**（不是生成一份带 ❌ 的文档）⇒ 逼着人更新。

## 数据来源

| 章节 | 来源 |
|---|---|
| 表归属 / 写入方 / 读取方 | ``emotion_cpt.contracts.tables.TABLES``（**代码**） |
| 共享表 / 反契约表 | ``emotion_cpt.contracts.shared_tables``（**代码**） |
| 契约项 → 上游位置 | 下表（**路径会逐个校验存在性**） |

用法::

    python scripts/gen_cross_references.py          # 写 docs/CROSS-REFERENCES.md
    python scripts/gen_cross_references.py --check  # 只校验，不写（CI 用）
"""

from __future__ import annotations

import argparse
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
CPT_REPO = pathlib.Path("/home/ubuntu/DSH/Chan_Pattern_Trader")
EMO_REPO = pathlib.Path("/home/ubuntu/DSH/emotion-core")

sys.path.insert(0, str(REPO / "src"))

from emotion_cpt.contracts import shared_tables, tables  # noqa: E402

#: 契约项 → (CPT 侧实现, emotion-core 侧实现)
#: ⚠️ **路径会被逐个校验**；上游挪了文件 ⇒ 这里失效 ⇒ 生成失败 ⇒ 逼着更新。
MAPPING: list[tuple[str, str, str, str]] = [
    (
        "**价格常量**（6 个）",
        "`cpt/application/track_points.py`（`from emotion_cpt.contracts.pricing import ...`）",
        "`src/emotion_core/algorithms/levels.py`（同上）",
        "`src/emotion_cpt/contracts/pricing.py`",
    ),
    (
        "**9 列封板快照**",
        "`cpt/storage/intraday_seal_store.py`（写入侧）",
        "`src/emotion_core/data/providers/cpt_intraday.py`（读取侧）",
        "`src/emotion_cpt/contracts/intraday_seal.py`",
    ),
    (
        "**取整位数** `PRICE_ROUND_DIGITS`",
        "`cpt/application/track_points.py`（经 `emotion_cpt.snapshot.points`）",
        "`src/emotion_core/algorithms/levels.py`（同上）",
        "`src/emotion_cpt/contracts/pricing.py`",
    ),
    (
        "**结构位算式**（P3 统一）",
        "`cpt/application/track_points.py`（`from emotion_cpt.snapshot.points import ...`）",
        "`src/emotion_core/algorithms/levels.py`（同上）",
        "`src/emotion_cpt/snapshot/points.py`",
    ),
    (
        "**A 股价制 / 涨跌停价口径**（P6）",
        "`cpt/domain/__init__.py`（**别名层**：`cpt.domain.price is emotion_cpt.structure.price`）",
        "`src/emotion_core/utils/price.py` + `src/emotion_core/algorithms/intraday.py`（转发层）",
        "`src/emotion_cpt/structure/price.py`"
        "（整数分算法；**Decimal 对照实现同在此文件**，逐分穷举一致）",
    ),
    (
        "**结构计算内核**（P2 搬迁）",
        "`cpt/domain/__init__.py`（**模块别名转发层**：`cpt.domain.X is emotion_cpt.structure.X`）",
        "—（情绪判据留在 emotion-core，不搬）",
        "`src/emotion_cpt/structure/`（17 模块）",
    ),
    (
        "**数据层**（`~/.dbconfig` 解析 / psycopg 参数）",
        "`cpt/adapters/_dbconfig.py`（旧副本）",
        "`src/emotion_core/utils/db.py`（旧副本）",
        "`src/emotion_cpt/db/config.py` + `connection.py`",
    ),
    (
        "**表 manifest**（47 张）",
        "—",
        "`src/emotion_core/data/schema.py`（DDL 侧）",
        "`src/emotion_cpt/contracts/tables.py`",
    ),
    (
        "**unit 真相源**（21 个）",
        "—",
        "—",
        "`src/emotion_cpt/deploy/systemd/`（随包分发）",
    ),
    (
        "**crontab 真相源**（16 条作业）",
        "—",
        "—",
        "`src/emotion_cpt/deploy/cron/crontab`（随包分发）",
    ),
]

HEADER = """# 交叉引用 —— 契约 ↔ 上游实现的对应关系

> **本文件是生成的**，别手改。
> 重算：`python scripts/gen_cross_references.py`（CI 用 `--check` 只校验）
>
> 路径在生成时**逐个校验存在性** ⇒ 上游挪了文件 ⇒ **生成失败**，
> 而不是产出一份指向空气的文档。

"""


def _extract_paths(cell: str) -> list[str]:
    """从表格单元格里抽出反引号里的路径（只取带 / 的，即路径而非标识符）。"""
    import re

    out = []
    for m in re.finditer(r"`([^`]+)`", cell):
        tok = m.group(1)
        if "/" in tok and not tok.startswith("("):
            out.append(tok)
    return out


def _check_paths() -> list[str]:
    """校验 MAPPING 里的路径真的存在。

    ⚠️ 语义要分清两种「不存在」：
    - **仓在、路径不在** ⇒ ❌ 失败（上游挪了文件 ⇒ 文档指向空气）
    - **仓不在本地**（CI 只 checkout 本仓）⇒ 跳过，并说明跳过原因
      ⇒ 否则 CI 上必然误报，门禁会被当成噪声忽略。
    """
    missing: list[str] = []
    skipped: list[str] = []
    for label, cpt, emo, own in MAPPING:
        for cell, root in ((cpt, CPT_REPO), (emo, EMO_REPO), (own, REPO)):
            paths = _extract_paths(cell)
            if not paths:
                continue
            if not root.is_dir():
                skipped.append(f"{label}: {root} 不在本地（跳过 {len(paths)} 个路径的校验）")
                continue
            for path in paths:
                if path.startswith("src/emotion_cpt/"):
                    target = REPO / path
                else:
                    target = root / path
                if not target.exists():
                    missing.append(f"{label}: {path}（在 {root} 下不存在）")
    for s in skipped:
        print(f"  (跳过：{s})")
    return missing


def _table_section() -> str:
    by_owner: dict[str, list] = {}
    for t in tables.TABLES:
        by_owner.setdefault(t.owner, []).append(t)

    lines = ["## 1. 表归属（47 张）", ""]
    lines.append("| 归属 | 张数 | 写入方 | 被谁读 |")
    lines.append("|---|---|---|---|")
    for owner, items in sorted(by_owner.items()):
        writers = sorted({t.writer for t in items})
        readers: dict[str, int] = {}
        for t in items:
            for rd in t.readers:
                readers[rd] = readers.get(rd, 0) + 1
        rd_txt = "、".join(f"{k} {v}" for k, v in sorted(readers.items()))
        lines.append(f"| **{owner}** | {len(items)} | {'、'.join(writers)} | {rd_txt} |")
    lines.append("")
    lines.append("### 逐表明细")
    lines.append("")
    lines.append("| 表 | 归属 | 写入方 | 读取方 | 遗留 |")
    lines.append("|---|---|---|---|---|")
    for t in sorted(tables.TABLES, key=lambda x: (x.owner, x.name)):
        lines.append(
            f"| `{t.name}` | {t.owner} | {t.writer} | {'、'.join(t.readers)} "
            f"| {'⚠️ 是' if t.legacy else '—'} |"
        )
    lines.append("")
    return "\n".join(lines)


def _shared_section() -> str:
    lines = ["## 2. 共享表与反契约表", ""]
    lines.append("| 表 | 方向 | 写入方 | 新鲜度日期列 | 数据来源 |")
    lines.append("|---|---|---|---|---|")
    for t in shared_tables.SHARED_TABLES:
        lines.append(f"| `{t.name}` | 共享 | {t.writer} | `{t.date_column}` | {t.source} |")
    for t in shared_tables.REVERSE_TABLES:
        lines.append(f"| `{t.name}` | **反契约** | {t.writer} | `{t.date_column}` | {t.source} |")
    lines.append("")
    return "\n".join(lines)


def _mapping_section() -> str:
    lines = ["## 3. 契约项 → 上游实现位置", ""]
    lines.append("| 契约项 | CPT 侧 | emotion-core 侧 | Emotion-CPT（唯一定义处） |")
    lines.append("|---|---|---|---|")
    for label, cpt, emo, own in MAPPING:
        lines.append(f"| {label} | {cpt} | {emo} | `{own}` |")
    lines.append("")
    return "\n".join(lines)


def build() -> str:
    parts = [HEADER, _table_section(), _shared_section(), _mapping_section()]
    parts.append(
        "## 4. 依赖方向（单向，不得成环）\n\n"
        "```\n"
        "CPT ────────┐\n"
        "            ├──▶ emotion_cpt（契约 / 数据层 / 结构内核 / 部署真相源）\n"
        "emotion-core┘\n"
        "```\n\n"
        "`emotion_cpt` **不 import 任何一方** ⇒ 不可能成环。\n"
        "门禁：`emotion_cpt.cli.check_contracts` 的「依赖方向」判据。\n"
    )
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验，不写")
    args = ap.parse_args()

    missing = _check_paths()
    if missing:
        print("❌ 交叉引用里的路径失效了（生成失败 ⇒ 别产出一份指向空气的文档）：")
        for m in missing:
            print(f"  · {m}")
        return 1
    print(f"✅ 交叉引用的 {len(MAPPING)} 组路径全部存在")

    body = build()
    out = REPO / "docs" / "CROSS-REFERENCES.md"
    if args.check:
        if not out.is_file() or out.read_text(encoding="utf-8") != body:
            print("❌ docs/CROSS-REFERENCES.md 与生成器输出不一致 ⇒ 需要重算")
            return 1
        print("✅ docs/CROSS-REFERENCES.md 与生成器一致")
        return 0

    out.write_text(body, encoding="utf-8")
    print(f"✅ 已生成 {out}（{len(body)} 字节）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
