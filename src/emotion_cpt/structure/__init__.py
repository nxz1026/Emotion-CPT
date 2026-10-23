"""结构计算内核 —— **缠论判据的唯一实现处**。

来源：CPT 的 ``cpt/domain/``（18 模块 / 3,581 行，**零三方依赖**，AST 实测）。
这是整个搬迁里**唯一干净的切口**：它不 import 任何上层，且 import-linter 契约
（``domain-has-no-third-party-deps`` 等三条）已经保证它不会依赖 storage / llm / adapters。

搬迁后 CPT 与 emotion-core 都从这里取分型/笔/中枢/背驰/趋势结构，
⇒ 「判据只许一处」在跨仓范围上第一次真正成立。
"""

from __future__ import annotations

__all__ = ["models", "rules"]
