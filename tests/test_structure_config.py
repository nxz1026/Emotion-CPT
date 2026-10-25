"""规则口径配置的**回放版本守卫**测试。

对应审计 **#4**：``RulesConfig.from_dict`` 原先把传入的 ``config_version``
**静默 pop 掉** ⇒ 异版本配置被当成当前版本接受 ⇒ 本模块头里承诺的
「回放 fixture 拒收异版本配置 / ``config_version`` 是回放入口的单点守卫」
**根本不存在**（``cpt.application.dashboard_reproducibility`` 的注释也写着
「``from_dict`` 会拒绝不匹配的 ``config_version``」
—— 两处文档都声称存在、代码里没有）。

危害具体是什么：``SCHEMA_VERSION`` 从 ``v0`` 升到 ``v1`` 的**唯一目的**
就是挡住「拿 v0 的 fixture 跑 v1 的代码还显示正常」，而这个机制是空的 ⇒
改了参数、版本号还是 v0 的旧 fixture 照样通过校验被回放，无任何提示。
"""

from __future__ import annotations

import pytest

from emotion_cpt.structure.config import SCHEMA_VERSION, RulesConfig


def test_current_version_is_v1() -> None:
    """版本号本身：门槛生效后结构不可比 ⇒ v0 fixture 作废 ⇒ 当前是 v1。"""
    assert SCHEMA_VERSION == "v1"


def test_from_dict_rejects_mismatched_version() -> None:
    """审计 #4：异版本配置必须**拒收**，而不是静默接受。"""
    with pytest.raises(ValueError, match="拒收异版本配置"):
        RulesConfig.from_dict({"config_version": "v0"})
    with pytest.raises(ValueError, match="拒收异版本配置"):
        RulesConfig.from_dict({"config_version": "v99"})


def test_from_dict_accepts_current_version() -> None:
    """版本号与当前一致 ⇒ 正常构造。"""
    config = RulesConfig.from_dict({"config_version": SCHEMA_VERSION})
    assert config.config_version == SCHEMA_VERSION


def test_from_dict_without_version_follows_code() -> None:
    """**没带**版本号 ⇒ 跟随代码（线上快照的 ``config`` 就是空的）。"""
    config = RulesConfig.from_dict({"min_bi_len": 4})
    assert config.config_version == SCHEMA_VERSION
    assert config.min_bi_len == 4


def test_from_dict_ignores_unknown_keys() -> None:
    """未知键被忽略（向前兼容：旧数据落入新版配置时丢弃多余字段）。"""
    config = RulesConfig.from_dict({"config_version": SCHEMA_VERSION, "某未来字段": 1})
    assert config.config_version == SCHEMA_VERSION


def test_to_dict_round_trip() -> None:
    """``to_dict`` → ``from_dict`` 往返必须原样（含版本号）。"""
    original = RulesConfig(min_bi_len=4)
    restored = RulesConfig.from_dict(original.to_dict())
    assert restored == original


def test_direct_construction_still_rejects_bad_version() -> None:
    """直接构造时版本不符仍报错（``__post_init__`` 那条路没被改）。"""
    with pytest.raises(ValueError, match="不支持的 config_version"):
        RulesConfig(config_version="v0")


# ────────────────────── 配置项的接线状态门禁 ──────────────────────


def _config_field_read_points(field: str) -> list[str]:
    """本仓（**除 config.py 自身**）里读这个字段的地方。

    ⚠️ config.py 自己的 ``if self.xxx < 1`` 是**值域校验**，不是「接线」
    ⇒ 排除它，否则每个字段都会被自己判成「已接线」。

    用 AST 找 ``ast.Attribute``（形如 ``cfg.xxx`` / ``self.xxx``）⇒
    **docstring 与注释里的提及不算**（那正是「文档说有、代码没有」的来源）。
    """
    import ast
    import pathlib

    from emotion_cpt.structure import config as cfg_mod

    pkg = pathlib.Path(cfg_mod.__file__).resolve().parent
    hits: list[str] = []
    for path in sorted(pkg.rglob("*.py")):
        if path.name == "config.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == field:
                hits.append(f"{path.name}:{node.lineno}")
                break
    return hits


def test_config_field_is_registered():
    """★ 每个 ``RulesConfig`` 字段都必须**明确登记**它的接线状态。

    背景（2026-10-25 静态审计 #6/#7/#10 + 复核）：
    ``RulesConfig`` 里好几项**能配但内核从不读** ⇒ 改了行为不变 ⇒ **假绿**。
    而接线又**不在本包**（在 CPT 的调用方）⇒ 只扫本包会误判。

    ⇒ 处置：每个字段必须落在**恰好一张**表里：
      - :data:`UNIMPLEMENTED_FIELDS` —— 真·没有落地点（配了也没用）
      - :data:`WIRED_BY_UPSTREAM` —— 本包不读、**上游在读**（语义生效）

    ⇒ **新加一个配置项却忘了登记 ⇒ 这里报红**（而不是等到有人以为它能配）。
    """
    import dataclasses

    from emotion_cpt.structure.config import (
        UNIMPLEMENTED_FIELDS,
        WIRED_BY_UPSTREAM,
        RulesConfig,
    )

    fields = [f.name for f in dataclasses.fields(RulesConfig)]
    registered = UNIMPLEMENTED_FIELDS | WIRED_BY_UPSTREAM
    both = UNIMPLEMENTED_FIELDS & WIRED_BY_UPSTREAM
    assert not both, f"同一个字段不能同时登记在两张表里：{sorted(both)}"

    missing = [name for name in fields if name not in registered]
    assert not missing, (
        f"这些配置字段**没有登记**接线状态：{missing}\n"
        "  ⇒ 新加字段忘了接线？它现在能配但没人读 ⇒ **假绿**。\n"
        "  ⇒ 请登记到 UNIMPLEMENTED_FIELDS（真没落地点）或 WIRED_BY_UPSTREAM（上游在读）。"
    )

    stale = [name for name in registered if name not in fields]
    assert not stale, f"登记表里有**已经不存在的字段**（该删了）：{sorted(stale)}"


def test_unimplemented_fields_really_have_no_read_point():
    """★ 登记为「没有落地点」的字段，**必须真的没有读取点**。

    ——防「登记了但其实已经实现了」⇒ 那样这张表就变成了永久的免死金牌。
    """
    from emotion_cpt.structure.config import UNIMPLEMENTED_FIELDS

    for name in sorted(UNIMPLEMENTED_FIELDS):
        hits = _config_field_read_points(name)
        assert not hits, (
            f"{name} 被登记为「没有落地点」，但本仓这里读它：{hits}\n"
            "  ⇒ 它其实已经接线了 ⇒ 请把它从 UNIMPLEMENTED_FIELDS 挪到 WIRED_BY_UPSTREAM。"
        )
