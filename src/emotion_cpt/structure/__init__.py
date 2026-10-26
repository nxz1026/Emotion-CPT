"""结构计算内核 —— **缠论判据的唯一实现处**。

来源：CPT 的 ``cpt/domain/``（18 模块 / 3,581 行，**零三方依赖**，AST 实测）。
这是整个搬迁里**唯一干净的切口**：它不 import 任何上层，且 import-linter 契约
（``domain-has-no-third-party-deps`` 等三条）已经保证它不会依赖 storage / llm / adapters。

搬迁后 CPT 与 emotion-core 都从这里取分型/笔/中枢/背驰/趋势结构，
⇒ 「判据只许一处」在跨仓范围上第一次真正成立。

⚠️ **本包是判据本体，不是转发层**。CPT 侧的 ``cpt.domain`` 是指向本包的**模块别名**。
"""

from __future__ import annotations

# ⚠️ 2026-10-26：本清单此前**还 import 着 521c51b 已从 git 删除的死模块**
#    （a_share_rules / containment_trace / levels / market_time / recursion /
#      signal / structure_events / trend_type）⇒ 新克隆的仓里那些模块根本不存在
#    ⇒ ``import emotion_cpt.structure`` **整个包 ImportError**（工作区当时
#    还能跑，只是靠磁盘上残留的旧副本撑着）。
#    ⇒ 这里与 521c51b 对齐：那批模块确实无人引用（CPT / emotion-core / portal
#    三仓实测零引用）⇒ 不再 import；它们的残留副本已移出仓库。
from . import (
    bi,
    config,
    contain,
    first_buy,
    fractal,
    intraday_rules,
    models,
    types,
    zhongshu,
)

__all__ = (
    "bi",
    "config",
    "contain",
    "first_buy",
    "fractal",
    "intraday_rules",
    "models",
    "types",
    "zhongshu",
)
