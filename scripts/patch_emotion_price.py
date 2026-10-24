#!/usr/bin/env python3
"""把 emotion-core 切到 Emotion-CPT 的统一价口径（P6 实质步骤）。

改动三处：

1. ``src/emotion_core/utils/price.py`` → **转发层**（唯一实现在 Emotion-CPT）
2. ``src/emotion_core/algorithms/intraday.py`` → ``board_pct_limit`` / ``is_st_name``
   转发到 ``emotion_cpt.structure.price``（值已穷举验证一致）
3. ``tests/caliber/test_price_unique_impl.py`` → 门禁改判：
   本仓内**不再有任何实现**；Python 侧前缀全集改从 Emotion-CPT 取
   （Rust 侧 ``board_pct_milli`` 必须覆盖它 —— **跨语言对等门禁不变**）

⚠️ 全部是**零行为变化**的转发：
- 整数分实现逐位相同（穷举 12 代码 × 6 名字 × 35 分位）
- 板制判定值逐条相同
"""

from __future__ import annotations

import pathlib
import sys

EMO = pathlib.Path("/home/ubuntu/DSH/emotion-core")

PRICE_FORWARD = '''"""涨停价唯一实现 —— **已迁至 Emotion-CPT**（2026-10-24）。

**唯一定义处**现在是 ``emotion_cpt.structure.price``（整数分运算）。
本文件保留为**转发层**，让仓内 4 个调用点零改动：

- ``algorithms/indicators.py``（模块级 import）
- ``algorithms/intraday.py``（模块级 import）
- ``presentation/server.py``（模块级 import）
- ``services/stock_service.py``（函数内 import）

## 为什么搬

此前**两套实现并存**（emotion-core 的整数分 vs CPT 的 Decimal），
跨仓对账用例虽能发现分歧，但那是**事后**；统一后是**事前**只有一份。

## 为什么保留转发层而不是改调用点

四个调用点分布在 algorithms / presentation / services 三层，
改它们会让 diff 变大、review 变难，而**转发层是零行为变化**：
``emotion_cpt.structure.price`` 的整数分实现与本仓原实现**逐分相同**
（穷举 12 个代码 × 6 个名字 × 35 个分位，见 Emotion-CPT 的
``tests/test_price_equivalence.py``）。

⚠️ 仓内那条「涨停价只许有一份实现」的 AST 门禁
（``tests/caliber/test_price_unique_impl.py``）已同步更新：
它现在断言**本仓内不再有任何实现**，且 Python 侧的前缀全集取自
Emotion-CPT —— **Rust 侧的 ``board_pct_milli`` 仍必须覆盖它**（跨语言对等门禁不变）。
"""

from __future__ import annotations

from emotion_cpt.structure.price import (
    board_pct_milli,
    is_limit_down,
    is_limit_up,
    limit_down_price_cents,
    limit_up_price_cents,
)

__all__ = (
    "board_pct_milli",
    "is_limit_down",
    "is_limit_up",
    "limit_down_price_cents",
    "limit_up_price_cents",
)
'''


def patch_price() -> None:
    p = EMO / "src" / "emotion_core" / "utils" / "price.py"
    p.write_text(PRICE_FORWARD, encoding="utf-8")
    print("  ✓ utils/price.py → 转发层")


def patch_intraday() -> None:
    p = EMO / "src" / "emotion_core" / "algorithms" / "intraday.py"
    s = p.read_text(encoding="utf-8")

    # ① board_pct_limit → 转发
    old = '''def board_pct_limit(code: str, *, name: str | None = None) -> float:'''
    assert old in s
    # 用整个函数体替换更稳：找到函数到下一个顶层 def
    start = s.index(old)
    end = s.index("\ndef is_st_name(", start)
    body = '''def board_pct_limit(code: str, *, name: str | None = None) -> float:
    """这只票的涨跌停幅度（百分比）。

    ★ 2026-10-24：口径已收敛到 Emotion-CPT（``emotion_cpt.structure.price``）——
    此前本仓与 CPT 各写一份，靠跨仓对账用例维持一致；现在是**同一份**。

    判定顺序即口径：

    1. 创业板 300/301、科创板 688/689 → 20%（ST 也是 20%）
    2. 北交所 920/8/4 → 30%（**ST 也是 30%** —— 北交所没有 5% 档）
    3. 主板 ST → 5%
    4. 其余 → 10%

    ⚠️ 顺序不能改：把 ST 提到最前 ⇒ 北交所 ST 落到 20%，算出**偏低的涨停价**，
    于是「已经封板」被误判成「还没到板」—— 方向比漏报更糟。

    :param name: 判断主板 ST 必须要它（代码里分不出 ST）。不传按「非 ST」算，
        这是**有意的乐观**：漏判 ST 得出偏高的涨停价（判不出封板），
        而不是偏低的（假封板）。宁可少报不可错报。
    """
    return _price.board_pct_limit(code, name=name)


'''
    s = s[:start] + body + s[end + 1 :]

    # ② is_st_name → 转发
    start = s.index("def is_st_name(name: str | None) -> bool:")
    end = s.index("\ndef is_main_board(", start)
    body = '''def is_st_name(name: str | None) -> bool:
    """名字里带 ST 就是 ST。**只能靠名字** —— 代码里没有任何 ST 信息。

    ★ 2026-10-24：口径已收敛到 Emotion-CPT（``emotion_cpt.structure.price``）。
    """
    return _price.is_st_name(name)


'''
    s = s[:start] + body + s[end + 1 :]

    # ③ 补 import
    old_imp = "from emotion_core.utils import price as price_util"
    new_imp = (
        "from emotion_core.utils import price as price_util\n"
        "\n"
        "# ★ 2026-10-24：口径唯一实现已收敛到 Emotion-CPT。\n"
        "# emotion_core.utils.price 现在是转发层；板制与 ST 判定的真源在那边。\n"
        "from emotion_cpt.structure import price as _price"
    )
    assert old_imp in s, "import 锚点未命中"
    s = s.replace(old_imp, new_imp, 1)

    # ④ 私有的 _PCT_LIMIT_* 常量不再被用（board_pct_limit 已转发）⇒ 删掉，避免死代码
    for name in ("_PCT_LIMIT_MAIN", "_PCT_LIMIT_GROWTH", "_PCT_LIMIT_BSE", "_PCT_LIMIT_ST"):
        import re

        s = re.sub(rf"(?m)^{name}: Final\[float\] = [0-9.]+\n", "", s)

    p.write_text(s, encoding="utf-8")
    print("  ✓ algorithms/intraday.py → board_pct_limit / is_st_name 转发")


def patch_gate() -> None:
    p = EMO / "tests" / "caliber" / "test_price_unique_impl.py"
    s = p.read_text(encoding="utf-8")

    # ① 文档头：说明唯一实现已迁到 Emotion-CPT
    old_head = '''"""口径守护：涨停价全项目唯一实现（AST 静态扫描）。'''
    new_head = '''"""口径守护：涨停价**全系统唯一实现**（AST 静态扫描）。

★ 2026-10-24：唯一实现已迁至 **Emotion-CPT**（``emotion_cpt.structure.price``）。
本仓的 ``utils/price.py`` 现在是**转发层** ⇒
「本仓内不得再有第二套实现」这条断言**依然成立且更有意义**。
Python 侧的前缀全集改从 Emotion-CPT 取 ⇒
「Rust 侧 board_pct_milli 必须覆盖 Python 侧前缀」这条**跨语言对等门禁不变**。

原始裁决（docs/13 §S2）：涨停价是 is_limit_up / 连板 / 家数判定的地基，错一分钱全错。'''
    assert old_head in s
    s = s.replace(old_head, new_head, 1)

    # ② PRICE_MODULE 指向 Emotion-CPT
    old = '''SRC = Path(__file__).resolve().parents[2] / "src" / "emotion_core"
PRICE_MODULE = SRC / "utils" / "price.py"'''
    new = '''SRC = Path(__file__).resolve().parents[2] / "src" / "emotion_core"
PRICE_MODULE = SRC / "utils" / "price.py"

#: ★ 唯一实现的**真源**（Emotion-CPT 已安装 ⇒ 从它的包位置取，不写死路径）
def _contract_price_module() -> Path:
    try:
        import emotion_cpt.structure.price as m
    except ImportError as exc:  # pragma: no cover - 契约包没装
        raise AssertionError(
            "emotion_cpt 没装 ⇒ 无法核对唯一实现（pip install -e ../Emotion-CPT）"
        ) from exc
    return Path(m.__file__).resolve()'''
    assert old in s
    s = s.replace(old, new, 1)

    # ③ 「只许定义一次」：本仓内不得有定义；真源在 Emotion-CPT
    old = '''def test_limit_price_functions_defined_once():
    defs: list[str] = []
    for path in _iter_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and (
                    node.name.startswith("limit_up_price")
                    or node.name.startswith("limit_down_price")):
                defs.append(f"{path}:{node.lineno} {node.name}")
    assert not defs, f"涨停/跌停价函数只许定义在 utils/price.py：{defs}"
    src = PRICE_MODULE.read_text(encoding="utf-8")
    assert "def limit_up_price_cents(" in src
    assert "def limit_down_price_cents(" in src'''
    new = '''def test_limit_price_functions_defined_once():
    """涨停/跌停价函数**本仓内不许有定义** —— 真源在 Emotion-CPT。

    （2026-10-24 之前是「只许定义在 utils/price.py」；那之后 utils/price.py
    变成转发层，唯一实现搬到 Emotion-CPT ⇒ 这条断言升级为「本仓内一个都不许有」。）
    """
    defs: list[str] = []
    for path in _iter_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and (
                    node.name.startswith("limit_up_price")
                    or node.name.startswith("limit_down_price")):
                defs.append(f"{path}:{node.lineno} {node.name}")
    assert not defs, (
        "涨停/跌停价的唯一定义处是 Emotion-CPT 的 emotion_cpt.structure.price，"
        f"本仓内不得再有实现：{defs}"
    )
    # 真源里必须有这两个函数
    src = _contract_price_module().read_text(encoding="utf-8")
    assert "def limit_up_price_cents(" in src
    assert "def limit_down_price_cents(" in src
    # 本仓的转发层必须真的转发（不是自己抄一遍）
    fwd = PRICE_MODULE.read_text(encoding="utf-8")
    assert "from emotion_cpt.structure.price import" in fwd, (
        "utils/price.py 必须是转发层（从 emotion_cpt.structure.price import）"
    )'''
    assert old in s
    s = s.replace(old, new, 1)

    # ④ 前缀抽取：改从 Emotion-CPT 取
    old = '''    tree = ast.parse(PRICE_MODULE.read_text(encoding="utf-8"))'''
    new = '''    tree = ast.parse(_contract_price_module().read_text(encoding="utf-8"))'''
    assert old in s
    s = s.replace(old, new, 1)

    old = '''    """从 utils/price.board_pct_milli 的 AST 抽出 {返回值: [前缀...]}。'''
    new = '''    """从 **Emotion-CPT** 的 ``structure.price.board_pct_milli``
    抽出 {返回值: [前缀...]}。'''
    assert old in s
    s = s.replace(old, new, 1)

    # ⑤ 展示层断言：转发后仍走 board_pct_milli（名字不变）
    old = '''    assert "board_pct_milli" in server, (
        "展示层涨停价文案必须由 utils/price 现算，不得写死 110")'''
    new = '''    assert "board_pct_milli" in server, (
        "展示层涨停价文案必须由价口径现算（现转发到 Emotion-CPT），不得写死 110")'''
    assert old in s
    s = s.replace(old, new, 1)

    p.write_text(s, encoding="utf-8")
    print("  ✓ tests/caliber/test_price_unique_impl.py → 门禁改判")


def main() -> int:
    patch_price()
    patch_intraday()
    patch_gate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
