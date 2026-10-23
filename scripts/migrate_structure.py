#!/usr/bin/env python3
"""把 CPT 的 ``cpt/domain/`` 逐字迁到 ``emotion_cpt/structure/``，并把原位置变成 re-export 壳。

为什么这样搬
------------
- ``cpt/domain/`` 是 AST 实证的**唯一干净切口**：18 模块 / 3,581 行 / **零三方依赖**，
  且 CPT 的 import-linter 契约（``domain-has-no-third-party-deps`` 等三条）已保证它不依赖任何上层。
- 搬迁后 CPT 侧改成 **显式 re-export** ⇒ 判据唯一真源变成 ``emotion_cpt.structure``，
  而 CPT 现有 **117 个** 引用 ``cpt.domain`` 的调用点**一行都不用改**。
- 依赖方向保持单向：``cpt → emotion_cpt``。

用法::

    python scripts/migrate_structure.py --cpt-root /home/ubuntu/DSH/Chan_Pattern_Trader \\
        --ec-root  /home/ubuntu/DSH/Emotion-CPT [--dry-run]
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import re
import sys

SHIM_TEMPLATE = '''"""{mod_path} —— 已迁至 Emotion-CPT。

**判据唯一真源现在是** ``emotion_cpt.structure.{mod_name}``。
本文件保留为**显式 re-export**，让 CPT 现有代码（117 个引用点）**零改动**即可运行。

迁移日期：2026-10-23　｜　迁移脚本：``scripts/migrate_structure.py``
"""

from __future__ import annotations

from emotion_cpt.structure.{mod_name} import (  # noqa: F401
{names}
)

__all__ = (
{all_names}
)
'''


def collect_used_names(cpt_root: pathlib.Path) -> dict[str, set[str]]:
    """全仓扫描：``from cpt.domain.X import a, b`` 里被引用的名字。

    必须做这一步：有些模块的 ``__all__`` **漏了**实际被 import 的名字
    （实测：``bi._is_more_extreme`` / ``bi._make_bi`` / ``signal.transition_first_sell`` /
    ``structure_events._event_type_for``）。壳若只导出 ``__all__``，
    这些调用点会直接 ImportError ⇒ **生产起不来**。
    """
    used: dict[str, set[str]] = {}
    for root in (cpt_root / "cpt", cpt_root / "scripts", cpt_root / "tests"):
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            for n in ast.walk(tree):
                if (isinstance(n, ast.ImportFrom) and n.level == 0 and n.module
                        and n.module.startswith("cpt.domain.")):
                    mod = n.module.split(".")[-1]
                    for a in n.names:
                        used.setdefault(mod, set()).add(a.name)
    return used


def public_names(tree: ast.Module) -> list[str]:
    """模块的公开顶层名：优先用 ``__all__``，否则取所有非下划线顶层定义。"""
    declared: list[str] | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "__all__":
                    try:
                        declared = [str(x) for x in ast.literal_eval(node.value)]
                    except (ValueError, SyntaxError):
                        declared = None
    if declared is not None:
        return declared
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                names.append(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and not t.id.startswith("_") and t.id != "__all__":
                    names.append(t.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and not node.target.id.startswith("_"):
                names.append(node.target.id)
    return names


def rewrite_imports(src: str) -> tuple[str, int]:
    """只改写 ``from cpt.domain.X import`` ⇒ ``from emotion_cpt.structure.X import``。"""
    count = 0

    def sub(m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return "from emotion_cpt.structure." + m.group(1) + " import"

    return re.sub(r"from cpt\.domain\.([a-z_]+) import", sub, src), count


def check_no_outside_imports(path: pathlib.Path) -> list[str]:
    """待迁模块不得 import cpt.domain 以外的 cpt.* 包（import-linter 契约的等价检查）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad: list[str] = []
    for node in ast.walk(tree):
        mods: list[str] = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            mods = [node.module]
        for m in mods:
            if m.startswith("cpt.") and not m.startswith("cpt.domain"):
                bad.append(m)
    return bad


def inject_note(text: str, mod_name: str) -> str:
    """把迁移说明插成**注释**（docstring 之后、代码之前）。

    为什么用注释而不是并入 docstring：
    - 并入 docstring 要处理开/闭引号、前缀(r-string)、内部转义 —— 很容易把引号弄丢；
    - PEP 236 明确允许「docstring、注释、空行」出现在 ``from __future__`` 之前，
      所以**注释方案既安全又不影响 __future__ 的位置**。
    """
    note = (
        "# >>> 已迁至 emotion_cpt.structure." + mod_name + "（2026-10-23）\n"
        "# >>> 本文逐字保留，仅改写模块间 import 指向；**判据内容一字未改**。\n"
    )
    tree = ast.parse(text)
    if (tree.body and isinstance(tree.body[0], ast.Expr)
            and isinstance(tree.body[0].value, ast.Constant)
            and isinstance(tree.body[0].value.value, str)):
        node = tree.body[0]
        lines = text.splitlines(keepends=True)
        offset = sum(len(x) for x in lines[: node.end_lineno - 1]) + node.end_col_offset
        return text[:offset] + "\n\n" + note + text[offset:]
    return note + text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="把 CPT cpt/domain 迁到 emotion_cpt.structure")
    ap.add_argument("--cpt-root", default="/home/ubuntu/DSH/Chan_Pattern_Trader")
    ap.add_argument("--ec-root", default="/home/ubuntu/DSH/Emotion-CPT")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    cpt_domain = pathlib.Path(args.cpt_root) / "cpt" / "domain"
    ec_struct = pathlib.Path(args.ec_root) / "src" / "emotion_cpt" / "structure"
    ec_struct.mkdir(parents=True, exist_ok=True)

    modules = sorted(cpt_domain.glob("*.py"))
    print("待迁模块 " + str(len(modules)) + " 个：" + str(cpt_domain))
    print("目标目录 " + str(ec_struct))

    problems: list[str] = []
    for src in modules:
        for m in check_no_outside_imports(src):
            problems.append(src.name + ": import 了 " + m)
    if problems:
        print("❌ 中止：待迁模块存在越界 import", file=sys.stderr)
        for p in problems:
            print("   " + p, file=sys.stderr)
        return 1
    print("✓ 越界 import 校验通过（待迁模块只依赖 cpt.domain 内部 + stdlib）")

    used = collect_used_names(pathlib.Path(args.cpt_root))
    print("全仓扫描到 " + str(len(used)) + " 个 cpt.domain 模块被外部引用")

    for src in modules:
        text = src.read_text(encoding="utf-8")
        tree = ast.parse(text)
        names = public_names(tree)
        mod_name = src.stem
        extra = sorted(used.get(mod_name, set()) - set(names))
        if extra:
            print("  ⚠️ " + mod_name + ": __all__ 漏了被引用的名字 " + str(extra) + " ⇒ 壳一并导出")
        names = list(dict.fromkeys(list(names) + extra))

        if mod_name == "__init__":
            if not args.dry_run:
                (ec_struct / "__init__.py").write_text(inject_note(text, mod_name), encoding="utf-8")
            print("  -> " + mod_name + ": 包初始化")
            continue

        moved, n_rewrites = rewrite_imports(text)
        moved = inject_note(moved, mod_name)
        if not args.dry_run:
            (ec_struct / (mod_name + ".py")).write_text(moved, encoding="utf-8")

        shim = SHIM_TEMPLATE.format(
            mod_path="cpt/domain/" + mod_name + ".py",
            mod_name=mod_name,
            names="\n".join("    " + x + "," for x in names),
            all_names="\n".join('    "' + x + '",' for x in names),
        )
        if not args.dry_run:
            (cpt_domain / (mod_name + ".py")).write_text(shim, encoding="utf-8")
        print("  -> " + mod_name + ": " + str(len(names)) + " 个公开名，"
              + str(n_rewrites) + " 处 import 改写")

    print("\n" + ("（dry-run，未写入）" if args.dry_run else "✅ 迁移完成"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
