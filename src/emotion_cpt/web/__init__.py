"""统一 web 入口 —— 门面层。

**「web 界面层抽离到 Emotion-CPT」的确切含义**：
本仓**不搬前端代码**。它持有的是**入口**：

- 统一门户：把各看板并列（``/``）
- 同票并排聚合页：三套口径逐字段对照（``/aggregate/stock/{code}``）
- 三个上游的 API 门面（``/api/aggregate/...``、``/api/health``）

两套前端（CPT 的原生 SPA / emotion 的 Jinja2 页面）**各自留在原处**，
由 nginx 各自反代到同一 origin 下。

**不合并进程**：保持 8010 / 8098 / 8091 三个独立故障域。
emotion-core 的 ``cpt_client`` 整套降级设计建立在「CPT 可能挂」这个前提上。
"""

from __future__ import annotations
