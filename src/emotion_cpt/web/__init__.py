"""统一 web 入口 —— 门面层。

**「web 界面层抽离到 Emotion-CPT」的确切含义**（避免误解）：
本仓**不搬前端代码**。它持有的是**入口**：
- 统一 origin 与认证（一个 nginx vhost / 一个反向代理）
- 门户：把各看板并列
- 聚合页：同票并排（CPT 结构 ∥ emotion 判据）
- **反向代理**：把两边的 API 与静态资源**挂载**到同一入口下

两套前端（CPT 的原生 SPA / emotion 的 Jinja2 页面）**各自保留在原处**，
作为静态资源被挂载。理由见 ``docs/CODE-FRAMEWORK.md`` §3：
CPT 的 web 层闭包达 98 模块 / 28,519 行，硬搬等于搬走 CPT 的 6/7 个包；
而"入口统一"这件事**一行前端代码都不用动**。

**不合并进程**：保持 8010 / 8098 / 8091 三个独立故障域。
emotion-core 的 ``cpt_client`` 整套降级设计建立在「CPT 可能挂」这个前提上。
"""

from __future__ import annotations

__all__ = ["aggregate", "facade"]
