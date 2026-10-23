"""入口门面 —— 路由表与挂载点。

挂载设计（同一 origin 下）::

    /                      门户（并列各看板入口）
    /aggregate/stock/{code} 同票并排聚合页
    /cpt/          ──反向代理──▶  127.0.0.1:8010   （CPT API + 静态看板）
    /emotion/      ──反向代理──▶  127.0.0.1:8098   （emotion API + Jinja 页面）
    /lab/          ──反向代理──▶  127.0.0.1:8091   （lab 只读面板）

**反向代理由 nginx 承担**（本仓只提供路由表与配置片段）——
理由：nginx 已经承担 TLS、auth_basic、Host 改写（插件门卫依赖），
在应用层重做一遍只会引入第二套不一致的规则。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

#: 上游各服务的回环地址。**只允许回环**，不接受调用方传 host
#: （沿用上游 cpt_client 的纪律：本设计不支持远程访问）。
CPT_BASE: Final[str] = "http://127.0.0.1:8010"
EMOTION_BASE: Final[str] = "http://127.0.0.1:8098"
LAB_BASE: Final[str] = "http://127.0.0.1:8091"

#: 回环请求超时上限。慢就是不正常。
DEFAULT_TIMEOUT: Final[float] = 3.0


@dataclass(frozen=True)
class Mount:
    """一个挂载点。"""

    prefix: str
    upstream: str
    description: str


MOUNTS: Final[tuple[Mount, ...]] = (
    Mount("/cpt/", CPT_BASE, "CPT 缠论结构看板（原生 SPA）"),
    Mount("/emotion/", EMOTION_BASE, "emotion-core 情绪判据看板（Jinja2 页面）"),
    Mount("/lab/", LAB_BASE, "emotion-core lab 只读实验面板"),
)


def nginx_location_snippets() -> str:
    """生成 nginx location 片段（供仓内 ``deploy/nginx/`` 维护）。"""
    lines: list[str] = []
    for mount in MOUNTS:
        target = mount.upstream.removeprefix("http://")
        lines.append(f"    # {mount.description}")
        lines.append(f"    location {mount.prefix} {{")
        lines.append(f"        proxy_pass http://{target}/;")
        lines.append("        proxy_http_version 1.1;")
        lines.append("        proxy_set_header Host $host;")
        lines.append("        proxy_set_header X-Real-IP $remote_addr;")
        lines.append("        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;")
        lines.append("        proxy_set_header X-Forwarded-Proto $scheme;")
        lines.append("        proxy_read_timeout 15s;")
        lines.append("    }")
    return "\n".join(lines)


__all__ = (
    "CPT_BASE",
    "DEFAULT_TIMEOUT",
    "EMOTION_BASE",
    "LAB_BASE",
    "MOUNTS",
    "Mount",
    "nginx_location_snippets",
)
