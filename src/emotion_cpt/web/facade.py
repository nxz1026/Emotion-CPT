"""统一入口的**挂载定义**与 nginx 片段生成。

## 拓扑

=============================  ==================  ==========================
路径                            上游                谁提供
=============================  ==================  ==========================
``/ecpt/``                      127.0.0.1:8092     **本门面**（门户 + 同票并排）
``/ecpt/cpt/``                  127.0.0.1:8010     CPT 看板（静态 + 只读 API）
``/ecpt/emotion/``              127.0.0.1:8098     emotion-core 看板
=============================  ==================  ==========================

⇒ 门户页把它们并列。
**不搬前端代码、不合并进程**：三套服务各自独立，故障域不变。

## 2026-10-26：``/dsh/`` 腾给 DeepSeek Harness

原 ``/dsh/`` 是本门面的**兼容别名**（旧链接不失效）⇒ 现在 ``/dsh/`` 归
**DeepSeek Harness**（DSH 本体）⇒ 本门面**只保留** ``/ecpt/`` 一个前缀。

⚠️ **语义翻转**：旧的 ``/dsh/`` 链接现在指向 DSH，不再指向 Emotion-CPT。
门面的三个入口（CPT / emotion / 同票并排）也一并**收编**进 ``/ecpt/``。

⚠️ CPT 与 emotion 的前端原先把 ``/cpt/``、``/emotion/`` **写死**在自己的
HTML/JS 里 ⇒ 收编后必须由前端**运行时推导**基址，否则资源与 API 会 404。
"""

from __future__ import annotations

import os
from typing import Final

#: 本门面的默认端口（8092；8091=lab / 8098=emotion 看板 / 8099=旧门户 / 8010=CPT）
DEFAULT_PORT: Final[int] = 8092
HOST: Final[str] = "127.0.0.1"

#: nginx 里本门面的前缀。
#: ⚠️ 2026-10-24：原为 ``/dsh/`` ⇒ 那是 dsh-web 平台的路径，与
#:    ``/emotion/``、``/cpt/`` **不对称**（那两个是项目名）。
#: ⇒ canonical 改成 ``/ecpt/``；``/dsh/`` 作为**兼容别名**保留（同样指向 8092）。
#: ⚠️ 2026-10-26：``/dsh/`` **正式归 DeepSeek Harness** ⇒ 兼容别名**取消**，
#:    本门面只剩 ``/ecpt/`` 一个前缀。
NGINX_PREFIX: Final[str] = "/ecpt/"

#: 门户里列的入口：``(路径, 名称, 说明, 标签)``
#:
#: ⚠️ 路径是**相对本门面挂载前缀**的 ⇒ 由 :func:`entry_href` 按请求前缀拼。
#: 2026-10-26 起 CPT / emotion **也收编**进 ``/ecpt/`` ⇒ 它们不再是
#: 「别的项目」，也就**不再需要**绝对路径（原 :data:`EXTERNAL_ENTRY_PREFIXES`）。
ENTRIES: Final[tuple[tuple[str, str, str, str], ...]] = (
    ("/cpt/", "CPT 缠论看板", "确定性分型/笔/中枢结构 + 买卖点", "结构分析"),
    ("/emotion/", "emotion-core 看板", "情绪周期、持仓决策、策略信号", "情绪选股"),
    ("/aggregate", "同票并排", "三套口径逐字段对照 —— 差异摆出来，不裁决", "统一对照"),
)


def entry_href(path: str, prefix: str = "") -> str:
    """门户上某个入口的 href。

    ⚠️ **入口必须按「当前请求的前缀」拼**：
    门面挂在 ``/ecpt/`` 下 ⇒ 写死 ``/cpt/`` 会落到 nginx 上**不存在**的 location
    ⇒ 点下去 404。

    ⇒ 前缀从 nginx 的 ``X-Forwarded-Prefix`` 头拿（直连 8092 时没有该头
    ⇒ 前缀为空 ⇒ 链接是根路径 ⇒ **自洽**）。
    """
    # ⚠️ 前缀为空（直连 8092，没有 X-Forwarded-Prefix 头）⇒ 用**绝对**根路径
    #   （写成相对路径浏览器也能解析，但**不直白**、也不好测）
    return (prefix or "/") + path.lstrip("/")


def nginx_location_snippet() -> str:
    """生成 nginx location 片段（供 ``deploy/nginx/`` 维护与 P7 的真相源归一）。

    ⚠️ 2026-10-26：这个函数曾经和 ``deploy/nginx/ecpt-facade.conf``
    **各写各的**（函数漏了 ``auth_basic`` 与 ``X-Forwarded-Prefix``，
    而提交进仓的片段有）⇒ 真相源漂移。
    ⇒ 现在两者内容**必须一致**，由 ``tests/test_facade.py`` 断言。
    """
    snippet_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "deploy",
        "nginx",
        "ecpt-facade.conf",
    )
    try:
        with open(snippet_path, encoding="utf-8") as handle:
            return handle.read().rstrip() + "\n"
    except OSError:
        # 装成 wheel 后仓内布局不存在 ⇒ 回落到内联片段（保底不崩）
        return f"""    # --- Emotion-CPT 统一门面（/ecpt/）---
    location {NGINX_PREFIX} {{
        auth_basic "Restricted";
        auth_basic_user_file /etc/nginx/.htpasswd;
        proxy_pass http://127.0.0.1:{DEFAULT_PORT}/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Prefix {NGINX_PREFIX};
        proxy_read_timeout 60s;
    }}"""


__all__ = (
    "DEFAULT_PORT",
    "ENTRIES",
    "HOST",
    "NGINX_PREFIX",
    "entry_href",
    "nginx_location_snippet",
)

