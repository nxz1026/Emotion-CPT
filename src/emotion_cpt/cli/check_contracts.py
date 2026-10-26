#!/usr/bin/env python3
"""契约门禁：把**跨项目契约**钉在上游的真实代码上。

## 它查什么（2026-10-24 改判据）

P3 之后，5 个价格常量在两个上游**都改成从契约包 import** 了 ⇒ 值不可能漂移
（值就是契约本身）。⇒ 漂移点变成了另外两个：

| # | 契约 | 上游的哪一处 | 漂了会怎样 |
|---|---|---|---|
| ① | **常量的来源** | CPT `cpt/application/track_points.py`<br>emotion-core `src/emotion_core/algorithms/levels.py` | 上游又**手抄**了一份字面量 ⇒ 两边算出不同的买/卖点价，**且没有任何测试会红** |
| ② | **9 列封板快照** | CPT `cpt/storage/intraday_seal_store.py`（写入侧）<br>emotion-core `src/emotion_core/data/providers/cpt_intraday.py`（读取侧） | 读方看到 ``None`` 列，**静默** |
| ③ | **契约版本** | 上游 `pyproject.toml` 里 pin 的 ``emotion-cpt @ ...@vX.Y.Z`` | 上游 pin 的契约比本仓旧 ⇒ 用的是旧判据，**却不报错** |
| ④ | **依赖方向** | 本仓自身 | 本仓 import 上游 ⇒ 依赖成环 |

## 为什么按「探测」而不是写死路径

本地是 ``DSH/Chan_Pattern_Trader`` + ``DSH/emotion-core`` 两个仓；
**CI 里一次只 checkout 一个仓**。所以同一份门禁要能：
- ``--upstream-root /home/ubuntu/DSH`` ⇒ 两个都查
- ``--upstream-root .`` ⇒ 只查当前这个仓（CI 用）

## 退出码

``0`` 无漂移；``1`` 有漂移（逐条列出）；``2`` 压根没找到可查的上游（**不算通过**）。
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import re
import sys
from dataclasses import dataclass
from typing import Any, Final

from emotion_cpt.contracts import intraday_seal, pricing

#: 上游仓 → 判定它「在不在」的特征文件（相对仓根）
_UPSTREAM_MARKERS: Final[dict[str, tuple[str, ...]]] = {
    "cpt": ("cpt/application/track_points.py", "cpt/storage/intraday_seal_store.py"),
    "emotion-core": (
        "src/emotion_core/algorithms/levels.py",
        "src/emotion_core/data/providers/cpt_intraday.py",
    ),
}

#: 上游仓 → 仓根的候选相对路径
_UPSTREAM_DIRS: Final[dict[str, tuple[str, ...]]] = {
    "cpt": ("Chan_Pattern_Trader",),
    "emotion-core": ("emotion-core",),
}

#: 上游仓 → 价格常量所在文件
_PRICE_FILE: Final[dict[str, str]] = {
    "cpt": "cpt/application/track_points.py",
    "emotion-core": "src/emotion_core/algorithms/levels.py",
}

#: 上游仓 → 封板快照列定义所在文件
_SEAL_FILE: Final[dict[str, str]] = {
    "cpt": "cpt/storage/intraday_seal_store.py",
    "emotion-core": "src/emotion_core/data/providers/cpt_intraday.py",
}

#: 要守「来源」的常量
_PRICE_CONSTS: Final[tuple[str, ...]] = (
    "BUY_BUFFER",
    "SELL_BUFFER",
    "STOP_LOSS_RATIO",
    "BI_LOOKBACK",
    "ZHONGSHU_LOOKBACK",
)

#: 契约常量所在的模块（上游必须从它 import）
_CONTRACT_MODULE: Final[str] = "emotion_cpt.contracts.pricing"


@dataclass
class Issue:
    """一条比对结果。"""

    kind: str
    where: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.kind}] {self.where}: {self.detail}"


def detect_upstreams(root: pathlib.Path) -> dict[str, pathlib.Path]:
    """探测 ``root`` 下有哪些上游仓 ⇒ ``{仓名: 仓根}``。"""
    found: dict[str, pathlib.Path] = {}
    for name, markers in _UPSTREAM_MARKERS.items():
        candidates = [root, *(root / d for d in _UPSTREAM_DIRS[name])]
        for candidate in candidates:
            if all((candidate / m).exists() for m in markers):
                found[name] = candidate
                break
    return found


def _parse(path: pathlib.Path) -> ast.Module | None:
    """解析源码；语法错 ⇒ None（**不抛** —— 门禁自己不能崩）。"""
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, ValueError, OSError, UnicodeDecodeError):
        return None


def _imports_from_contract(tree: ast.Module) -> set[str]:
    """这个文件从契约包 import 了哪些名字。"""
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in (
            _CONTRACT_MODULE,
            "emotion_cpt.contracts",
        ):
            out.update(a.name for a in node.names)
    return out


def _referenced_names(tree: ast.Module) -> set[str]:
    """这个文件里**真正被读到**的名字（排除定义本身与 import 语句）。"""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            bound.update(a.asname or a.name for a in node.names)
        elif isinstance(node, ast.Import):
            bound.update((a.asname or a.name).split(".")[0] for a in node.names)
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
    return used - bound


def _local_literals(path: pathlib.Path) -> dict[str, Any]:
    """这个文件里**本地定义**的模块级常量（手抄的痕迹）。"""
    tree = _parse(path)
    if tree is None:
        return {}
    out: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        if node.value is None:
            continue
        try:
            out[node.target.id] = ast.literal_eval(node.value)
        except (ValueError, SyntaxError):
            continue
    return out


def _tuple_of_names(path: pathlib.Path, var: str) -> tuple[str, ...]:
    """提取一个模块级元组常量的字符串元素（如 ``_COLUMNS``）。"""
    tree = _parse(path)
    if tree is None:
        return ()
    for node in tree.body:
        targets: list[ast.expr] = []
        stmt_value: ast.expr | None = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
            stmt_value = node.value
        elif isinstance(node, ast.Assign):
            targets = list(node.targets)
            stmt_value = node.value
        for t in targets:
            if not isinstance(t, ast.Name) or t.id != var or stmt_value is None:
                continue
            try:
                value = ast.literal_eval(stmt_value)
            except (ValueError, SyntaxError):
                continue
            if isinstance(value, (tuple, list)):
                return tuple(str(v) for v in value)
    return ()


def _column_lists(path: pathlib.Path) -> list[tuple[str, ...]]:
    """找出文件里**所有**「像列清单」的常量。

    为什么这么挑：
    - **只看模块级赋值**（``Assign`` / ``AnnAssign``）—— 文档字符串里的散文
      （如「R93 起写 9 列：``at, code, ...``」）不是列清单，扫到它是**假阳性**；
    - 列名清单在 CPT 那边有**两处**（``_SELECT_COLS`` 与 ``_INSERT_SQL``），
      只查一处 ⇒ 另一处改了不会被发现；
    - **允许含未知列名**（如把 ``is_st`` 改成 ``is_st_x``）—— 否则真漂移反��检测不到。
      判据是「≥5 段且其中 ≥4 段是已知列名」。
    """
    tree = _parse(path)
    if tree is None:
        return []
    known = {c.name for c in intraday_seal.INTRADAY_SEAL_COLUMNS}
    out: list[tuple[str, ...]] = []
    for node in tree.body:
        value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
        if value is None:
            continue
        parts: list[str] | None = None
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            text = value.value
            if "INSERT INTO" in text and "intraday_seal_snapshot" in text:
                # ⚠️ INSERT 语句是**多个字面量拼接**的，AST 会折叠成一个常量 ——
                #    整串里还含 ``ON CONFLICT (at, code)``，用 rsplit(")") 会把它吃进来。
                # ⇒ 精确取「表名后面第一个括号组」：列清单里没有嵌套括号。
                marker = "intraday_seal_snapshot ("
                if marker in text:
                    inner = text.split(marker, 1)[-1].split(")", 1)[0]
                    parts = [c.strip() for c in inner.split(",")]
                else:
                    parts = [c.strip() for c in text.split(",")]
            else:
                parts = [c.strip() for c in text.split(",")]
        elif isinstance(value, (ast.Tuple, ast.List)):
            try:
                parts = [str(x) for x in ast.literal_eval(value)]
            except (ValueError, SyntaxError):
                parts = None
        if not parts:
            continue
        parts = [p.strip().strip('"').strip("'") for p in parts]
        parts = [p for p in parts if p and p.isidentifier()]
        if len(parts) < 5:
            continue
        if sum(1 for p in parts if p in known) < 4:
            continue
        out.append(tuple(parts))
    seen: set[tuple[str, ...]] = set()
    uniq: list[tuple[str, ...]] = []
    for item in out:
        if item not in seen:
            seen.add(item)
            uniq.append(item)
    return uniq


def check_constant_sources(upstreams: dict[str, pathlib.Path]) -> list[Issue]:
    """① 上游的价格常量**必须从契约包 import**，不得本地手抄。"""
    issues: list[Issue] = []
    for name, root in upstreams.items():
        rel = _PRICE_FILE[name]
        path = root / rel
        if not path.exists():
            issues.append(Issue("missing", f"{name}/{rel}", "文件不存在，无法校验"))
            continue
        tree = _parse(path)
        if tree is None:
            issues.append(Issue("unparsable", f"{name}/{rel}", "源码无法解析（语法错？）"))
            continue
        imported = _imports_from_contract(tree)
        local = _local_literals(path)
        used = _referenced_names(tree)
        for cname in _PRICE_CONSTS:
            # 只查**这个文件真正用到**的常量 —— CPT 的 track_points 不需要
            # BI_LOOKBACK（那俩是私有的，且计算已搬走），强求反而是假阳性。
            if cname not in used and cname not in local:
                continue
            if cname in local:
                issues.append(
                    Issue(
                        "handwritten",
                        f"{name}/{rel}:{cname}",
                        f"本地定义了 {cname}={local[cname]!r} ⇒ 必须改成从 "
                        f"`{_CONTRACT_MODULE}` import，否则两侧会各自漂",
                    )
                )
            elif cname not in imported:
                issues.append(
                    Issue(
                        "missing",
                        f"{name}/{rel}:{cname}",
                        f"既没从契约包 import、也没本地定义 ⇒ 找不到 {cname}",
                    )
                )
    return issues


def check_contract_values(upstreams: dict[str, pathlib.Path]) -> list[Issue]:
    """①b 契约本身的值与「本仓认定的值」一致（防有人改了 pricing.py 却没想清楚）。"""
    issues: list[Issue] = []
    expected = {
        "BUY_BUFFER": pricing.BUY_BUFFER,
        "SELL_BUFFER": pricing.SELL_BUFFER,
        "STOP_LOSS_RATIO": pricing.STOP_LOSS_RATIO,
        "BI_LOOKBACK": pricing.BI_LOOKBACK,
        "ZHONGSHU_LOOKBACK": pricing.ZHONGSHU_LOOKBACK,
    }
    for cname, want in expected.items():
        if want is None:
            issues.append(Issue("missing", "emotion_cpt.contracts.pricing", f"{cname} 未定义"))
    return issues


def check_seal_columns(upstreams: dict[str, pathlib.Path]) -> list[Issue]:
    """② 9 列封板快照（写入侧 vs 读取侧 vs 契约）。"""
    issues: list[Issue] = []
    want = tuple(c.name for c in intraday_seal.INTRADAY_SEAL_COLUMNS)

    for name in ("cpt", "emotion-core"):
        root = upstreams.get(name)
        if root is None:
            continue
        rel = _SEAL_FILE[name]
        lists = _column_lists(root / rel)
        if not lists:
            issues.append(Issue("missing", f"{name}/{rel}", "未解析到任何列清单"))
            continue
        for got in lists:
            if got != want:
                issues.append(
                    Issue("drift", f"{name}/{rel}", f"列清单={list(got)} 契约={list(want)}")
                )
    return issues


def check_pinned_versions(upstreams: dict[str, pathlib.Path]) -> list[Issue]:
    """③ 上游 pin 的契约版本不能落后于本仓当前 tag。"""
    issues: list[Issue] = []
    current = _current_tag()
    for name, root in upstreams.items():
        pyproject = root / "pyproject.toml"
        if not pyproject.exists():
            continue
        text = pyproject.read_text(encoding="utf-8")
        m = re.search(r'emotion-cpt\s*@\s*[^"\'\s]*@([A-Za-z0-9._-]+)', text)
        if not m:
            issues.append(
                Issue(
                    "unpinned",
                    f"{name}/pyproject.toml",
                    "没有声明 emotion-cpt 依赖（契约不受版本约束）",
                )
            )
            continue
        pinned = m.group(1)
        if current and pinned and _norm_version(pinned) != _norm_version(current):
            issues.append(
                Issue(
                    "stale-pin",
                    f"{name}/pyproject.toml",
                    f"pin 的契约版本是 {pinned}，本仓当前是 {current} ⇒ 上游用的是旧判据",
                )
            )
    return issues


def _norm_version(v: str) -> tuple[int, ...]:
    """版本号归一：``v0.1.0`` / ``0.1.0`` ⇒ 同一个东西。"""
    cleaned = v.strip().lstrip("vV")
    parts: list[int] = []
    for chunk in cleaned.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _current_tag() -> str | None:
    """本仓（契约包）当前版本。

    **优先用 ``importlib.metadata``** —— CI 里契约包是**非 editable** 安装的
    （``pip install "emotion-cpt @ git+…"`），那时 ``__file__`` 落在 site-packages 里，
    读不到 ``pyproject.toml`` ⇒ 版本检查会被**静默跳过**。
    ⇒ 先问已安装的元数据，再退回仓内 pyproject。
    """
    # ① 开发检出（editable / 源码树运行）⇒ 以**源码里的 pyproject** 为准。
    #    ⚠️ editable 安装的 .dist-info 里版本是**安装那一刻**的，pyproject 改了它不会变
    #    ⇒ 只看元数据会误报 stale-pin（2026-10-24 实测踩过）。
    pyproject = pathlib.Path(__file__).resolve().parents[3] / "pyproject.toml"
    if pyproject.exists():
        m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    # ② 装成包（CI 场景）⇒ 以**已安装的元数据**为准
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("emotion-cpt")
        except PackageNotFoundError:
            return None
    except Exception:  # noqa: BLE001
        return None


def check_no_upstream_imports() -> list[Issue]:
    """④ 依赖方向：本仓不得 import 上游。"""
    issues: list[Issue] = []
    pkg = pathlib.Path(__file__).resolve().parents[2]
    banned = {"cpt", "emotion_core"}
    for path in sorted(pkg.rglob("*.py")):
        if "tests" in path.parts:
            continue
        tree = _parse(path)
        if tree is None:
            issues.append(Issue("unparsable", str(path), "源码无法解析（语法错？）"))
            continue
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in banned:
                    issues.append(
                        Issue(
                            "forbidden-import",
                            str(path),
                            f"不得 import 上游模块 {name!r}",
                        )
                    )
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="契约一致性门禁（只读）")
    parser.add_argument(
        "--upstream-root",
        default="/home/ubuntu/DSH",
        help="上游仓所在根目录；CI 里用 ``.``（只 checkout 了一个仓）",
    )
    args = parser.parse_args(argv)

    root = pathlib.Path(args.upstream_root).resolve()
    upstreams = detect_upstreams(root)
    if not upstreams:
        print(
            f"❌ 在 {root} 下没有找到任何可校验的上游仓"
            f"（期望特征：{list(_UPSTREAM_MARKERS)}）",
            file=sys.stderr,
        )
        return 2

    issues: list[Issue] = []
    issues += check_constant_sources(upstreams)
    issues += check_contract_values(upstreams)
    issues += check_seal_columns(upstreams)
    issues += check_pinned_versions(upstreams)
    issues += check_no_upstream_imports()

    if issues:
        print(f"❌ 契约漂移 {len(issues)} 条（检查了 {', '.join(upstreams)}）：", file=sys.stderr)
        for issue in issues:
            print(f"  {issue}", file=sys.stderr)
        return 1
    print(
        f"✅ 契约一致：常量来源 / 9 列封板快照 / 契约版本 / 依赖方向"
        f"（检查了 {', '.join(upstreams)}）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
