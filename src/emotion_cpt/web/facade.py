"""统一入口的**挂载定义**与 nginx 片段生成。

## 拓扑

===========================  ==================  =========================
路径                          上游                谁提供
===========================  ==================  =========================
``/cpt/``                     127.0.0.1:8010     nginx 既有反代（CPT 自带看板）
``/emotion/``                 127.0.0.1:8098     nginx 既有反代（emotion-core 看板）
``/lab/``                     127.0.0.1:8091     nginx 既有反代（emotion-core 实验面板）
``/ecpt/``                    127.0.0.1:8092     **本门面**（门户 + 同票并排）
``/dsh/``                     127.0.0.1:8092     兼容别名（同上，旧链接不失效）
===========================  ==================  =========================

⇒ 四个入口在**同一个 origin** 下，门户页把它们并列。
**不搬前端代码、不合并进程**：三套服务各自独立，故障域不变。
"""

from __future__ import annotations

from typing import Final

#: 本门面的默认端口（8092；8091=lab / 8098=emotion 看板 / 8099=旧门户 / 8010=CPT）
DEFAULT_PORT: Final[int] = 8092
HOST: Final[str] = "127.0.0.1"

#: nginx 里本门面的前缀。
#: ⚠️ 2026-10-24：原为 ``/dsh/`` ⇒ 那是 dsh-web 平台的路径，与
#:    ``/emotion/``、``/cpt/`` **不对称**（那两个是项目名）。
#: ⇒ canonical 改成 ``/ecpt/``；``/dsh/`` 作为**兼容别名**保留（同样指向 8092）。
NGINX_PREFIX: Final[str] = "/ecpt/"

#: 门户里列的入口：``(路径, 名称, 说明, 标签)``
ENTRIES: Final[tuple[tuple[str, str, str, str], ...]] = (
    ("/cpt/", "CPT 缠论看板", "确定性分型/笔/中枢结构 + 买卖点", "结构分析"),
    ("/emotion/", "emotion-core 看板", "情绪周期、持仓决策、策略信号", "情绪选股"),
    ("/aggregate", "同票并排", "三套口径逐字段对照 —— 差异摆出来，不裁决", "统一对照"),
)


#: **别的项目**的入口前缀 —— 它们的 location 在 nginx 上 ⇒ 必须**绝对路径**。
#: （本门面的入口不在这里 ⇒ 走 :func:`entry_href` 按当前挂载前缀拼。）
EXTERNAL_ENTRY_PREFIXES: Final[tuple[str, ...]] = ("/cpt/", "/emotion/")


def entry_href(path: str, prefix: str = "") -> str:
    """门户上某个入口的 href。

    ⚠️ **本门面的入口必须按「当前请求的前缀」拼**：
    门面**同时**挂在 ``/ecpt/``（canonical）与 ``/dsh/``（兼容别名）下
    ⇒ 写死任何一个都会让另一个坏。

    ⇒ 前缀从 nginx 的 ``X-Forwarded-Prefix`` 头拿（直连 8092 时没有该头
    ⇒ 前缀为空 ⇒ 链接是根路径 ⇒ **自洽**）。

    ⇒ 别的项目（``/cpt/``、``/emotion/``）是**它们自己的** nginx location
    ⇒ 保持**绝对路径**，别加前缀。
    """
    if path.startswith(EXTERNAL_ENTRY_PREFIXES):
        return path
    # ⚠️ 前缀为空（直连 8092，没有 X-Forwarded-Prefix 头）⇒ 用**绝对**根路径
    #   （写成相对路径浏览器也能解析，但**不直白**、也不好测）
    return (prefix or "/") + path.lstrip("/")


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


__all__ = (
    "DEFAULT_PORT",
    "ENTRIES",
    "EXTERNAL_ENTRY_PREFIXES",
    "HOST",
    "NGINX_PREFIX",
    "entry_href",
    "nginx_location_snippet",
)
