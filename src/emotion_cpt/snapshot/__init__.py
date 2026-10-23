"""快照 —— 把「K 线 → 结构 → 结论」这条链的**计算部分**收拢到一处。

来源：CPT ``cpt/application/a_share_snapshot.py``（1,959 行）与其依赖的 domain 内核，
以及 ``cpt/storage/{dashboard_run_store,run_metric_store}.py`` 的写入部分。

**关键区分**（这决定搬迁规模）：
- **计算部分**（分型/笔/中枢/背驰/结构位/买卖点判定）⇒ 搬进本仓
- **取数部分**（行情源 adapters：东财/新浪/pytdx/binance）⇒ **留在 CPT**
  （那是"连哪取数"，与"怎么算结构"是两件事）
- **落库部分**（``cpt_dashboard_run`` / ``cpt_run_metric`` 的写入）⇒ 走本仓的数据层，
  但**表的归属仍在 CPT**（manifest 已登记）

搬迁后，CPT 的 ``a_share_snapshot`` 会从 1,959 行的厚编排，变成调用
``emotion_cpt.snapshot`` 的薄壳。
"""

from __future__ import annotations

__all__ = ["pipeline"]
