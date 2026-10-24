"""★ 文档漂移门禁的**自证**：注入假数据 ⇒ 门禁必须报错。

纪律来源：上游 R45 —— *「自制的验证工具第一版基本都错」*。
**跑全绿不够，必须注入假数据确认它还能报。**

这个门禁自己就是被 R45 教出来的：它的**第一版**把「当前状态」和
「历史陈述」搞混了 —— 同一个「5 个价格常量」，
在 README 的「迁移前痛点表」里是**历史陈述**（当时确实 5 个），
在「产出物清单」里是**当前声明**（现在是 6 个）。
正则分不清这两者 ⇒ 第一版只能靠人判断 ⇒ 误报满天飞 ⇒ 门禁会被无视。

⇒ 第二版改成 **contract-facts 块**：写了就等于声明「这是当前事实」，
历史陈述不在块里 ⇒ 自动豁免，且豁免**显式可审计**。

这里全部用**合成的小目录**（不碰真实仓）：

- ``tmp/docs/``  —— 假文档
- ``tmp/``       —— 假仓根（文件清单判据要看文件真的在不在）
"""

from __future__ import annotations

import pathlib

from emotion_cpt.cli import check_doc_drift as cdd

#: 一份**干净**的 contract-facts 块（值取自真实代码，测试里不改代码）
GOOD_FACTS = """<!-- contract-facts
tables: 47
columns: 9
constants: 6
shared_tables: 7
reverse_tables: 1
owner_emotion: 37
owner_cpt: 9
owner_reverse: 1
-->
"""


def _write(root: pathlib.Path, name: str, body: str) -> pathlib.Path:
    d = root / "docs"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(body, encoding="utf-8")
    return p


def _run(root: pathlib.Path) -> list[str]:
    return cdd.check_all(root / "docs", root)


# ─────────────────────────── 正向 ───────────────────────────


def test_clean_doc_passes() -> None:
    """一份与代码一致的文档 ⇒ 一条问题都不该有。"""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        _write(root, "CONTRACTS.md", f"# 契约\n\n{GOOD_FACTS}\n")
        assert _run(root) == []


# ─────────────────────────── J0 · 事实块 ───────────────────────────


def test_facts_block_with_wrong_number_is_flagged() -> None:
    """事实块里的数字写错 ⇒ 必须报。"""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        bad = GOOD_FACTS.replace("tables: 47", "tables: 46")
        _write(root, "CONTRACTS.md", f"# 契约\n\n{bad}\n")
        issues = _run(root)
        assert any("tables" in i and "46" in i for i in issues), issues


def test_facts_block_missing_key_is_flagged() -> None:
    """事实块少一个键 ⇒ 声明不完整 ⇒ 必须报（不能当成"没声明"混过去）。"""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        partial = "\n".join(
            line for line in GOOD_FACTS.splitlines() if not line.startswith("columns:")
        )
        _write(root, "CONTRACTS.md", f"# 契约\n\n{partial}\n")
        issues = _run(root)
        assert any("缺键" in i and "columns" in i for i in issues), issues


def test_no_facts_block_anywhere_is_flagged() -> None:
    """**一份事实块都没有** ⇒ 契约数字没有机器可读真源 ⇒ 必须报。

    ⚠️ 这一条是防「门禁自己被架空」：没有事实块时，
    数字对账就完全失效了 —— 而门禁还会显示「全绿」。
    """
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        _write(root, "README.md", "# 契约总览\n\n52 张表，9 列。\n")
        issues = _run(root)
        assert any("没有机器可读的真源" in i for i in issues), issues


# ─────────────────────────── J1 · 列定义镜像 ───────────────────────────


def test_column_semantics_mismatch_is_flagged() -> None:
    """文档贴的列语义与代码不一致 ⇒ 必须报。"""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        body = f"""# 契约

{GOOD_FACTS}

```python
Column("distance_pct", "double precision", True, unit="百分数（非小数）",
       semantics="(limit-price)/limit*100；0.0=封在板上，负数=已超板"),
```
"""
        _write(root, "CONTRACTS.md", body)
        issues = _run(root)
        assert any("distance_pct" in i and "semantics" in i for i in issues), issues


def test_doc_missing_unit_is_flagged() -> None:
    """★ 代码里有 `unit` 而文档没写 ⇒ 必须报。

    这是**最贵的那种漂移**：`bid1_lots` 的单位是「手」不是「股」，
    文档若漏了它 ⇒ 读方按「股」实现 ⇒ 阈值算错 100 倍，
    **而且没有任何测试会红**。
    """
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        body = f"""# 契约

{GOOD_FACTS}

```python
Column("bid1_lots", "double precision", True,
       semantics="买一挂单量；读方阈值用股时必须 ×100"),
```
"""
        _write(root, "CONTRACTS.md", body)
        issues = _run(root)
        assert any("bid1_lots" in i and "unit" in i for i in issues), issues


def test_doc_mentions_unknown_column_is_flagged() -> None:
    """文档写了代码里没有的列 ⇒ 必须报。"""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        body = f"""# 契约

{GOOD_FACTS}

```python
Column("bid1_volume", "double precision", True, semantics="手抄出来的列名"),
```
"""
        _write(root, "CONTRACTS.md", body)
        issues = _run(root)
        assert any("bid1_volume" in i for i in issues), issues


# ─────────────────────────── J2 · 常量镜像 ───────────────────────────


def test_constant_value_mismatch_is_flagged() -> None:
    """文档里常量的值写错 ⇒ 必须报。"""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        body = f"""# 契约

{GOOD_FACTS}

```python
BUY_BUFFER = 1.05
```
"""
        _write(root, "CONTRACTS.md", body)
        issues = _run(root)
        assert any("BUY_BUFFER" in i for i in issues), issues


# ─────────────────────────── J5 · 文件清单 ───────────────────────────


def test_tree_file_that_does_not_exist_is_flagged() -> None:
    """文档的目录树列了不存在的文件 ⇒ 必须报。"""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        body = f"""# 契约

{GOOD_FACTS}

```
Emotion-CPT/
└── src/emotion_cpt/
    └── contracts/
        └── totally_not_here.py
```
"""
        _write(root, "CONTRACTS.md", body)
        issues = _run(root)
        assert any("totally_not_here.py" in i for i in issues), issues


def test_tree_file_that_exists_is_not_flagged() -> None:
    """反向：真存在的文件不该被误报。"""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        target = root / "src" / "emotion_cpt" / "contracts"
        target.mkdir(parents=True)
        (target / "pricing.py").write_text("", encoding="utf-8")
        body = f"""# 契约

{GOOD_FACTS}

```
Emotion-CPT/
└── src/emotion_cpt/
    └── contracts/
        └── pricing.py
```
"""
        _write(root, "CONTRACTS.md", body)
        assert _run(root) == []


def test_upstream_tree_is_not_checked() -> None:
    """★ 文档里画的**上游**的树不该被当成本仓的文件去查。

    P7 文档里提到 `scripts/cron_daily_report.py` —— 那是 **CPT 仓**的。
    本仓没有它 ⇒ 查了就误报。⇒ 只有根是本仓名的树才校验。
    """
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        body = f"""# 契约

{GOOD_FACTS}

```
Chan_Pattern_Trader/
└── scripts/
    └── cron_daily_report.py
```
"""
        _write(root, "CONTRACTS.md", body)
        assert _run(root) == []
