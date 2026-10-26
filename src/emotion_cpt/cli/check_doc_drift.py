#!/usr/bin/env python3
"""文档 ↔ 代码 的漂移门禁。

## 为什么需要它

文档里写着「52 张表 / 9 列 / 7 张共享表」—— 这些数字**本身也是一份副本**。
代码改了、文档没改 ⇒ 谁都看不出来，直到有人照着文档去核对、发现对不上，
或者更糟：**照着过期文档做决策**。

⚠️ 这正是本仓一直在吃的亏的文档版本：
contract 里 `bid1_lots` 的单位是「手」，文档若写成「股」，
读方按文档实现 ⇒ 阈值算错 100 倍，**且没有任何测试会红**。

## 判据（5 条）

| # | 判据 | 抓什么 |
|---|---|---|
| J0 | **事实块** | 文档里 ``contract-facts`` 块声明的每个数字与代码一致；**且必须存在这样的块** |
| J1 | **列定义镜像** | 文档 python 块里的 ``Column(...)`` 与代码**逐字段**一致；且代码里有 `unit`/`semantics` 而文档没写 ⇒ 红（文档漏了语义/单位 = 最贵的漂移） |
| J2 | **契约常量镜像** | 文档 python 块里的契约常量与代码**值**一致 |
| J5 | **文件清单** | 文档里点名的本仓文件（契约模块 / 门禁脚本）必须**真的存在** |

## 关键设计①：**数字只留一处，且机器可读**

⚠️ 散落在散文里的数字**没法自动对账** —— 同一个「5 个价格常量」：
- 在「迁移前的痛点」表里是**历史陈述**（当时确实 5 个）
- 在「产出物清单」里是**当前声明**（现在是 6 个）

正则分不清这两者 ⇒ 只能靠人判断 ⇒ 那就**不让它需要判断**。

⇒ 契约数字集中到 ``docs/CONTRACTS.md`` 的一个 **contract-facts 块**：

```markdown
<!-- contract-facts
tables: 52
columns: 9
constants: 6
-->
```

写了就等于声明「**这是当前事实**」；门禁逐项对账。
⇒ 历史陈述不在块里 ⇒ 自动豁免，且**豁免是显式的**（块写不写、写了什么，一眼可见）。

## 关键设计②：**门禁不硬编码「52」**

它从块里把数字**抽出来**，再跟代码对账。
⇒ 文档改了数字但代码没改 ⇒ 红；代码改了但文档没改 ⇒ 也红。**两头都堵。**

## 退出码

``0`` 无漂移；``1`` 有漂移（逐条列出，带 ``文件:行``）；``2`` 找不到文档目录（**不算通过**）。
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import re
import sys
from typing import Any, Final

from emotion_cpt.contracts import intraday_seal, pricing, shared_tables, tables

#: 仓根（``docs/`` 在仓根，不在包里 —— 文档是仓库资产）
_REPO_ROOT: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]

#: contracts/pricing 的常量（本项目语境里「常量」指的就是这批）
_PRICING_CONSTANTS: Final[dict[str, Any]] = {
    n: getattr(pricing, n)
    for n in dir(pricing)
    if n.isupper() and not n.startswith("_")
}

#: 契约常量：文档里出现就必须与代码一致
_CONTRACT_CONSTANTS: Final[dict[str, Any]] = {
    "INTRADAY_SEAL_TABLE": intraday_seal.INTRADAY_SEAL_TABLE,
    **_PRICING_CONSTANTS,
}

#: contract-facts 块里可用的键 → 代码事实
#: ⚠️ 这里**只声明「键叫什么」**，不声明「值是多少」—— 值从文档抽。
_FACT_KEYS: Final[dict[str, Any]] = {
    "tables": lambda: len(tables.TABLES),
    "columns": lambda: len(intraday_seal.INTRADAY_SEAL_COLUMNS),
    "constants": lambda: len(_PRICING_CONSTANTS),
    "shared_tables": lambda: len(shared_tables.SHARED_TABLES),
    "reverse_tables": lambda: len(shared_tables.REVERSE_TABLES),
    "owner_emotion": lambda: _owner_counts()["emotion-core"],
    # ⚠️ 「CPT 自有」**不含**反契约表（`intraday_seal_snapshot` 由 CPT 写、emotion 读，
    #    但它是**反契约表**，文档里单列）⇒ 口径 = cpt 桶 − 反契约表
    "owner_cpt": lambda: _owner_counts()["cpt"] - len(shared_tables.REVERSE_TABLES),
    "owner_reverse": lambda: len(shared_tables.REVERSE_TABLES),
}

#: contract-facts 块必须**齐全**（少一个键 ⇒ 门禁不认这份声明）
_REQUIRED_FACT_KEYS: Final[tuple[str, ...]] = (
    "tables",
    "columns",
    "constants",
    "shared_tables",
    "reverse_tables",
    "owner_emotion",
    "owner_cpt",
    "owner_reverse",
)

#: 块的写法：``<!-- contract-facts`` … ``-->``
_FACTS_RE: Final[re.Pattern[str]] = re.compile(
    r"<!--\s*contract-facts\s*\n(.*?)-->", re.S
)

#: J5 里算「本仓文件」的前缀
# ⚠️ **刻意不含 "scripts/"** —— `scripts/` 在 CPT 与 Emotion-CPT 里都存在
#    （P7 文档里提到的 `scripts/cron_daily_report.py` 是 **CPT 仓的**）
#    ⇒ 按路径判「是不是本仓的」会误报。本仓脚本清单由**目录树**判据管
#    （树以仓名为根，不会认错）。
_OWN_PATHS: Final[tuple[str, ...]] = (
    "src/emotion_cpt/",
    "contracts/",
    "deploy/",
)


# ──────────────────────────── 工具 ────────────────────────────


def _py_blocks(text: str) -> list[str]:
    return re.findall(r"```python\n(.*?)```", text, re.S)


def _paragraph_of(text: str, pos: int) -> str:
    """取包含 ``pos`` 的那一段（空行分段）。"""
    start = text.rfind("\n\n", 0, pos) + 2
    end = text.find("\n\n", pos)
    if end == -1:
        end = len(text)
    return text[start:end]


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _code_columns() -> dict[str, dict[str, Any]]:
    return {
        c.name: {
            "dtype": c.dtype,
            "nullable": c.nullable,
            "unit": c.unit,
            "semantics": c.semantics,
        }
        for c in intraday_seal.INTRADAY_SEAL_COLUMNS
    }


def _doc_columns(text: str) -> dict[str, dict[str, Any]]:
    """从文档的 python 代码块里抽出 ``Column(...)`` 定义。"""
    out: dict[str, dict[str, Any]] = {}
    for block in _py_blocks(text):
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue  # 片段不是完整 python（文档里很常见）
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "Column"
            ):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            name = str(node.args[0].value)
            fields: dict[str, Any] = {}
            if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                fields["dtype"] = node.args[1].value
            if len(node.args) > 2 and isinstance(node.args[2], ast.Constant):
                fields["nullable"] = node.args[2].value
            for kw in node.keywords:
                if kw.arg is None:
                    continue
                try:
                    fields[kw.arg] = ast.literal_eval(kw.value)
                except (ValueError, SyntaxError):
                    fields[kw.arg] = ast.unparse(kw.value)
            out[name] = fields
    return out


def _doc_constants(text: str) -> dict[str, Any]:
    """从文档的 python 代码块里抽出契约常量的赋值。"""
    out: dict[str, Any] = {}
    for block in _py_blocks(text):
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            if target.id not in _CONTRACT_CONSTANTS:
                continue
            try:
                out[target.id] = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                out[target.id] = ast.unparse(node.value)
    return out


#: 本仓的仓名（目录树以它为根 ⇒ 那棵树才是「本仓的树」，才可校验）
_REPO_NAME: Final[str] = "Emotion-CPT"


def _doc_tree_files(text: str) -> list[str]:
    """从**本仓的**目录树代码块里抽出文件（相对仓根的路径）。

    ⚠️ 只处理根是本仓的树 —— 文档里也会画**上游**的树（``cpt/``、``emotion-core/``），
    那些文件不在本仓，校验它们只会满屏误报。
    """
    out: list[str] = []
    for block in re.findall(r"```\n(.*?)```", text, re.S):
        if "├──" not in block and "└──" not in block:
            continue
        lines = block.splitlines()
        root = lines[0].strip() if lines else ""
        if root.rstrip("/").split("/")[-1].lower() != _REPO_NAME.lower():
            continue  # 不是本仓的树
        # 栈：(缩进, 目录名)
        stack: list[tuple[int, str]] = []
        for line in lines[1:]:
            if not line.strip():
                continue
            lead = line.lstrip("│ ├└─")
            indent = len(line) - len(lead)
            name = re.split(r"\s+(?:#|←)", lead)[0].strip()
            if not name:
                continue
            while stack and stack[-1][0] >= indent:
                stack.pop()
            if name.endswith("/"):
                stack.append((indent, name))
            else:
                parent = "".join(n for _i, n in stack)
                rel = parent + name
                if rel.lower().startswith(_REPO_NAME.lower() + "/"):
                    rel = rel[len(_REPO_NAME) + 1 :]
                out.append(rel)
    return out


# ──────────────────────────── 判据 ────────────────────────────


def check_columns(doc: str, rel: str) -> list[str]:
    """J1 · 列定义镜像。"""
    issues: list[str] = []
    code_cols = _code_columns()
    doc_cols = _doc_columns(doc)
    for name, dfields in sorted(doc_cols.items()):
        cfields = code_cols.get(name)
        if cfields is None:
            issues.append(f"{rel}: 文档写了列 {name!r}，代码里没有")
            continue
        for key in ("dtype", "nullable", "unit", "semantics"):
            if key not in dfields:
                # 文档没提 ⇒ 代码里若非空 ⇒ 文档漏了单位/语义
                if cfields.get(key) not in (None, ""):
                    issues.append(
                        f"{rel}: 文档的 Column({name!r}) 漏了 {key}"
                        f"（代码里是 {cfields[key]!r}）—— 同名不同义是最贵的漂移"
                    )
                continue
            if dfields[key] != cfields.get(key):
                issues.append(
                    f"{rel}: Column({name!r}) 的 {key} 不一致："
                    f"文档 {dfields[key]!r} vs 代码 {cfields.get(key)!r}"
                )
    return issues


def check_constants(doc: str, rel: str) -> list[str]:
    """J2 · 契约常量镜像。"""
    issues: list[str] = []
    for name, value in _doc_constants(doc).items():
        expected = _CONTRACT_CONSTANTS[name]
        if value != expected:
            issues.append(f"{rel}: 常量 {name} 不一致：文档 {value!r} vs 代码 {expected!r}")
    return issues


def _owner_counts() -> dict[str, int]:
    from emotion_cpt.schema.manifest import summary

    return {k: v.get("total", 0) for k, v in summary().items()}


def _doc_facts(doc: str) -> dict[str, str]:
    """抽出文档里的 ``contract-facts`` 块（键 → 值原文）。"""
    out: dict[str, str] = {}
    for m in _FACTS_RE.finditer(doc):
        for line in m.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


def check_facts(doc: str, rel: str) -> tuple[list[str], bool]:
    """J0 · contract-facts 块：逐项对账 + 键必须齐全。

    返回 ``(问题列表, 是否声明了事实块)``。
    """
    issues: list[str] = []
    facts = _doc_facts(doc)
    if not facts:
        return issues, False
    for key in _REQUIRED_FACT_KEYS:
        if key not in facts:
            issues.append(f"{rel}: contract-facts 块缺键 {key!r}（声明不完整 ⇒ 不认这份）")
    for key, raw in sorted(facts.items()):
        if key not in _FACT_KEYS:
            issues.append(f"{rel}: contract-facts 里有不认识的键 {key!r}")
            continue
        expected = _FACT_KEYS[key]()
        try:
            claimed = int(raw)
        except ValueError:
            issues.append(f"{rel}: contract-facts 的 {key} 不是整数：{raw!r}")
            continue
        if claimed != expected:
            issues.append(
                f"{rel}: contract-facts 的 {key} = {claimed}，代码是 {expected}"
            )
    return issues, True


def check_files(doc: str, rel: str, repo_root: pathlib.Path) -> list[str]:
    """J5 · 文件清单：文档点名的本仓文件必须真的存在。"""
    issues: list[str] = []

    # 5a. 反引号里的完整路径
    for m in re.finditer(r"`([A-Za-z0-9_./-]+\.(?:py|sh|toml|json|md))`", doc):
        path = m.group(1)
        if not path.startswith(_OWN_PATHS):
            continue  # 上游的路径，不在本仓
        if "*" in path:
            continue  # 通配符（如 deploy/cron/*.sh）不是单个文件
        if not (repo_root / path).is_file():
            issues.append(
                f"{rel}:{_line_of(doc, m.start())}: 文档提到本仓文件 {path!r}，"
                f"但它不存在"
            )

    # 5b. 目录树里的叶子（本仓的树）
    for path in _doc_tree_files(doc):
        if not path or "*" in path:
            continue  # 通配符（如 deploy/cron/*.sh）不是单个文件
        if (repo_root / path).is_file():
            continue
        issues.append(f"{rel}: 文档的目录树列了 {path}，但它不存在")
    return issues


# ──────────────────────────── 主流程 ────────────────────────────


#: 历史文档的**显式**豁免标记（写在文件顶部的 HTML 注释里）
#: 例：``<!-- doc-drift-exempt: P0 当时的真实状态，改它等于改历史 -->``
#:
#: ⚠️ 豁免必须是**显式的、可审计的**：文件里写着为什么豁免，
#: 门禁运行时也会把被豁免的文件**打印出来** ⇒ 不会变成隐式后门。
_EXEMPT_MARK: Final[str] = "doc-drift-exempt"


def check_all(docs_dir: pathlib.Path, repo_root: pathlib.Path) -> list[str]:
    issues: list[str] = []
    docs = sorted(p for p in docs_dir.rglob("*.md") if p.is_file())
    readme = repo_root / "README.md"
    if readme.is_file():
        docs.append(readme)
    declared = 0
    for p in docs:
        rel = str(p.relative_to(repo_root))
        text = p.read_text(encoding="utf-8")
        if _EXEMPT_MARK in text:
            print(f"  (豁免：{rel} —— 文件里写明了豁免理由)")
            continue
        issues.extend(check_columns(text, rel))
        issues.extend(check_constants(text, rel))
        issues.extend(check_files(text, rel, repo_root))
        fact_issues, has_facts = check_facts(text, rel)
        issues.extend(fact_issues)
        if has_facts:
            declared += 1
    if declared == 0:
        issues.append(
            "没有任何文档声明 contract-facts 块 ⇒ 契约数字**没有机器可读的真源**，"
            "文档漂移无法判定（请在 docs/CONTRACTS.md 里加一块）"
        )
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="文档 ↔ 代码 漂移门禁")
    parser.add_argument(
        "--docs-dir",
        default=str(_REPO_ROOT / "docs"),
        help="文档目录（默认：仓根 docs/）",
    )
    parser.add_argument(
        "--repo-root",
        default=str(_REPO_ROOT),
        help="仓根（用于校验文档点名的文件是否真的存在）",
    )
    args = parser.parse_args(argv)

    docs_dir = pathlib.Path(args.docs_dir)
    repo_root = pathlib.Path(args.repo_root)

    if not docs_dir.is_dir():
        print(
            f"❌ 找不到文档目录：{docs_dir} —— 文档漂移**无法判定**，"
            f"这不算通过",
            file=sys.stderr,
        )
        return 2

    issues = check_all(docs_dir, repo_root)
    if issues:
        print(f"❌ 文档与代码漂移（{len(issues)} 项）：", file=sys.stderr)
        for i in issues:
            print(f"  · {i}", file=sys.stderr)
        return 1

    n_docs = len(list(docs_dir.rglob("*.md")))
    print(
        f"✅ 文档与代码一致（{n_docs} 篇文档 + README；"
        f"事实块 / 列定义 / 常量 / 文件清单 4 类判据全过）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
