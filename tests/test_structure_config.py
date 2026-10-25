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
