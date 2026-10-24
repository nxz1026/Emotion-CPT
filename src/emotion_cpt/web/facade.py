"""统一入口的**挂载定义**与 nginx 片段生成。

## 拓扑

===========================  ==================  =========================
路径                          上游                谁提供
===========================  ==================  =========================
``/cpt/``                     127.0.0.1:8010     nginx 既有反代（CPT 自带看板）
``/emotion/``                 127.0.0.1:8098     nginx 既有反代（emotion-core 看板）
``/lab/``                     127.0.0.1:8091     nginx 既有反代（emotion-core 实验面板）
``/dsh/``                     127.0.0.1:8092     **本门面**（门户 + 同票并排）
===========================  ==================  =========================

⇒ 四个入口在**同一个 origin** 下，门户页把它们并列。
**不搬前端代码、不合并进程**：三套服务各自独立，故障域不变。
"""

from __future__ import annotations

from typing import Final

#: 本门面的默认端口（8092；8091=lab / 8098=emotion 看板 / 8099=旧门户 / 8010=CPT）
DEFAULT_PORT: Final[int] = 8092
HOST: Final[str] = "127.0.0.1"

#: nginx 里本门面的前缀
NGINX_PREFIX: Final[str] = "/dsh/"

#: 门户里列的入口：``(路径, 名称, 说明, 标签)``
ENTRIES: Final[tuple[tuple[str, str, str, str], ...]] = (
    ("/cpt/", "CPT 缠论看板", "确定性分型/笔/中枢结构 + 买卖点", "结构分析"),
    ("/emotion/", "emotion-core 看板", "情绪周期、持仓决策、策略信号", "情绪选股"),
    ("/aggregate", "同票并排", "三套口径逐字段对照 —— 差异摆出来，不裁决", "统一对照"),
)


def nginx_location_snippet() -> str:
    """生成 nginx location 片段（供 ``deploy/nginx/`` 维护与 P7 的真相源归一）。"""
    return f"""    # --- Emotion-CPT 统一门面（2026-10-24）---
    # 门户 + 同票并排聚合页。**只读**。
    location {NGINX_PREFIX} {{
        proxy_pass http://127.0.0.1:{DEFAULT_PORT}/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }}"""


__all__ = ("DEFAULT_PORT", "ENTRIES", "HOST", "NGINX_PREFIX", "nginx_location_snippet")
