"""契约门禁：把本仓的契约与**上游两侧的实际代码**逐条比对。

漂移的方向有两边，所以两边都要查：
- 上游 CPT 改了 ``BUY_BUFFER``，emotion 的手抄副本没改 ⇒ 两侧与本仓三方不一致
- 上游 emotion 改了 ``_COLUMNS``，CPT 的 ``_INSERT_SQL`` 没改 ⇒ 列清单不一致

**只读**：全程只解析源码 AST，不 import 上游、不写任何文件。

用法::

    python -m emotion_cpt.cli.check_contracts --upstream-root /home/ubuntu/DSH
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import sys
from dataclasses import dataclass
from typing import Any

from emotion_cpt.contracts import intraday_seal, pricing

#: 上游仓名 → 相对 DSH 根的路径
_UPSTREAMS = {
    "cpt": "Chan_Pattern_Trader",
    "emotion-core": "emotion-core",
}

#: 价格常量在两侧的文件路径（相对各上游仓根）
_PRICE_FILES = {
    "cpt": "cpt/application/track_points.py",
    "emotion-core": "src/emotion_core/algorithms/levels.py",
}

#: intraday_seal 列清单在两侧的文件路径
_SEAL_FILES = {
    "cpt": "cpt/storage/intraday_seal_store.py",
    "emotion-core": "src/emotion_core/data/providers/cpt_intraday.py",
}

_PRICE_CONSTS = ("BUY_BUFFER", "SELL_BUFFER", "STOP_LOSS_RATIO", "BI_LOOKBACK", "ZHONGSHU_LOOKBACK")


#: 哨兵：区分「值恰好是 None」与「没找到」
_MISSING: Any = object()


@dataclass
class Issue:
    """一条比对结果。"""

    kind: str
    where: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.kind}] {self.where}: {self.detail}"


def _module_constants(path: pathlib.Path) -> dict[str, Any]:
    """从源码里提取模块级常量（``NAME: Final[...] = <literal>``）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
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
    """从源码里提取一个模块级元组常量的字符串元素（如 ``_COLUMNS``）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        targets: list[ast.expr] = []
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
        elif isinstance(node, ast.Assign):
            targets = list(node.targets)
        for t in targets:
            if not isinstance(t, ast.Name) or t.id != var or node.value is None:
                continue
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                continue
            if isinstance(value, (tuple, list)):
                return tuple(str(v) for v in value)
    return ()


def _insert_sql_columns(path: pathlib.Path) -> tuple[str, ...]:
    """从 CPT 的 ``_INSERT_SQL`` 里抽出列名序列。"""
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if "INSERT INTO" in value and "intraday_seal_snapshot" in value:
                head = value.split("(", 1)[-1]
                cols = head.split(")", 1)[0]
                names = [c.strip().strip('"') for c in cols.split(",")]
                return tuple(n for n in names if n and not n.startswith("--"))
    return ()


def check_prices(root: pathlib.Path) -> list[Issue]:
    """比对 5 个价格常量：契约 ↔ CPT 真源 ↔ emotion 手抄副本。"""
    issues: list[Issue] = []
    expected = {
        "BUY_BUFFER": pricing.BUY_BUFFER,
        "SELL_BUFFER": pricing.SELL_BUFFER,
        "STOP_LOSS_RATIO": pricing.STOP_LOSS_RATIO,
        "BI_LOOKBACK": pricing.BI_LOOKBACK,
        "ZHONGSHU_LOOKBACK": pricing.ZHONGSHU_LOOKBACK,
    }
    for upstream, rel in _PRICE_FILES.items():
        path = root / _UPSTREAMS[upstream] / rel
        if not path.exists():
            issues.append(Issue("missing", f"{upstream}/{rel}", "文件不存在，无法校验"))
            continue
        consts = _module_constants(path)
        for name, want in expected.items():
            # 上游的命名不完全一致：emotion 用 ``BI_LOOKBACK``，
            # CPT 用 ``_BI_LOOKBACK``（模块私有前缀）。两种都认。
            got = consts.get(name, consts.get(f"_{name}", _MISSING))
            if got is _MISSING:
                issues.append(Issue("missing", f"{upstream}/{rel}", f"常量 {name} 未找到"))
                continue
            if got != want:
                issues.append(
                    Issue(
                        "drift",
                        f"{upstream}/{rel}:{name}",
                        f"上游={got!r} 契约={want!r} —— 不一致",
                    )
                )
    return issues


def check_seal_columns(root: pathlib.Path) -> list[Issue]:
    """比对 9 列：契约 ↔ CPT 的 INSERT 列 ↔ emotion 的读列。"""
    issues: list[Issue] = []
    want = tuple(c.name for c in intraday_seal.INTRADAY_SEAL_COLUMNS)

    cpt_path = root / _UPSTREAMS["cpt"] / _SEAL_FILES["cpt"]
    if cpt_path.exists():
        got = _insert_sql_columns(cpt_path)
        if not got:
            issues.append(Issue("missing", f"cpt/{_SEAL_FILES['cpt']}", "未解析到 INSERT 列清单"))
        elif got != want:
            issues.append(
                Issue("drift", f"cpt/{_SEAL_FILES['cpt']}", f"写入列={list(got)} 契约={list(want)}")
            )
    else:
        issues.append(Issue("missing", f"cpt/{_SEAL_FILES['cpt']}", "文件不存在，无法校验"))

    emo_path = root / _UPSTREAMS["emotion-core"] / _SEAL_FILES["emotion-core"]
    if emo_path.exists():
        got = _tuple_of_names(emo_path, "_COLUMNS")
        if not got:
            issues.append(
                Issue("missing", f"emotion-core/{_SEAL_FILES['emotion-core']}", "未解析到 _COLUMNS")
            )
        elif got != want:
            issues.append(
                Issue(
                    "drift",
                    f"emotion-core/{_SEAL_FILES['emotion-core']}",
                    f"读取列={list(got)} 契约={list(want)}",
                )
            )
    else:
        issues.append(
            Issue("missing", f"emotion-core/{_SEAL_FILES['emotion-core']}", "文件不存在，无法校验")
        )
    return issues


def check_no_upstream_imports() -> list[Issue]:
    """本仓不得 import 上游（依赖方向纪律）。"""
    issues: list[Issue] = []
    pkg = pathlib.Path(__file__).resolve().parents[2]
    banned = {"cpt", "emotion_core"}
    for path in sorted(pkg.rglob("*.py")):
        if "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in banned:
                    issues.append(
                        Issue("forbidden-import", str(path), f"不得 import 上游模块 {name!r}")
                    )
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="契约一致性门禁（只读）")
    parser.add_argument(
        "--upstream-root",
        default="/home/ubuntu/DSH",
        help="上游仓所在根目录（默认 /home/ubuntu/DSH）",
    )
    args = parser.parse_args(argv)

    root = pathlib.Path(args.upstream_root)
    issues: list[Issue] = []
    issues += check_prices(root)
    issues += check_seal_columns(root)
    issues += check_no_upstream_imports()

    if issues:
        print(f"❌ 契约漂移 {len(issues)} 条：", file=sys.stderr)
        for issue in issues:
            print(f"  {issue}", file=sys.stderr)
        return 1
    print("✅ 契约一致：5 个价格常量 / 9 列封板快照 / 依赖方向 均无漂移")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
