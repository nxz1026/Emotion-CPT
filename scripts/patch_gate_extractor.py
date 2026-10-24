#!/usr/bin/env python3
"""修 emotion-core 门禁的「前缀提取器」：让它能解析**命名常量**的返回值。

## 问题

提取器只认 ``ast.Constant`` 的返回值：

    if code.startswith("bj"):
        return _PCT_MILLI_BSE      # ← 名字，不是字面量 ⇒ 抽不出 ⇒ 返回空 ⇒ 自检报警

Emotion-CPT 的实现用**命名常量**（更可读），于是提取器空转 ——
而这条测试自己的 docstring 就写着「提取器自身不许空转…这类『断言了但什么都没断言』的
测试比没有测试更危险」。

⇒ 修法：解析模块级常量，把 ``Name`` 返回值解析成它指向的 int。
**不是放宽判据，是让提取器真的能提取。**
"""

from __future__ import annotations

import pathlib
import sys

TARGET = pathlib.Path(
    "/home/ubuntu/DSH/emotion-core/tests/caliber/test_price_unique_impl.py"
)

OLD = '''    tree = ast.parse(_contract_price_module().read_text(encoding="utf-8"))
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "board_pct_milli")
    out: dict[int, list[str]] = {}
    for node in fn.body:
        if not isinstance(node, ast.If):
            continue
        ret = next((s for s in node.body if isinstance(s, ast.Return)), None)
        call = next((s for s in ast.walk(node.test)
                     if isinstance(s, ast.Call) and _is_starts_with(s.func)), None)
        if (ret is None or call is None
                or not isinstance(ret.value, ast.Constant)
                or not isinstance(ret.value.value, int)):
            continue'''

NEW = '''    src = _contract_price_module().read_text(encoding="utf-8")
    tree = ast.parse(src)

    # ★ 模块级命名常量：名字 → int（Emotion-CPT 的实现用命名常量，
    #   提取器若只认字面量就会抽出空字典 ⇒ 后续对等断言**空转通过**。
    #   这条测试自己的 docstring 写过：「断言了但什么都没断言的测试比没有测试更危险」。
    consts: dict[str, int] = {}
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        if node.value is None:
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, SyntaxError):
            continue
        if isinstance(value, int) and not isinstance(value, bool):
            consts[node.target.id] = value

    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "board_pct_milli")
    out: dict[int, list[str]] = {}
    for node in fn.body:
        if not isinstance(node, ast.If):
            continue
        ret = next((s for s in node.body if isinstance(s, ast.Return)), None)
        call = next((s for s in ast.walk(node.test)
                     if isinstance(s, ast.Call) and _is_starts_with(s.func)), None)
        if ret is None or call is None:
            continue
        if isinstance(ret.value, ast.Constant):
            value = ret.value.value
        elif isinstance(ret.value, ast.Name):
            value = consts.get(ret.value.id)
        else:
            continue
        if not isinstance(value, int) or isinstance(value, bool):
            continue'''


def main() -> int:
    s = TARGET.read_text(encoding="utf-8")
    if "consts: dict[str, int] = {}" in s:
        print("  (已打过补丁,跳过)")
        return 0
    assert OLD in s, "提取器段未命中"
    TARGET.write_text(s.replace(OLD, NEW, 1), encoding="utf-8")
    print("  ✓ 提取器已支持命名常量")
    return 0


if __name__ == "__main__":
    sys.exit(main())
