"""对两个上游的**只读** HTTP 客户端。

**硬约束**（逐条抄自上游 ``emotion_core/services/cpt_client.py`` 的设计要求，
因为那些约束是被真实事故打出来的）：

1. 只用标准库 ``urllib.request``
2. **绝不抛** —— 任何失败返回 ``None`` + 结构化的「不可用原因」
   （CPT 挂了也必须能出结果，走降级）
3. **只允许回环** —— host 由模块常量拼，**不接受调用方传 host**
4. **只调读端点** —— 本聚合页不写任何数据
5. 不缓存 —— 快照随行情变
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Final

log = logging.getLogger("emotion_cpt.web.aggregate")

CPT_BASE: Final[str] = "http://127.0.0.1:8010"
EMOTION_BASE: Final[str] = "http://127.0.0.1:8098"
TIMEOUT: Final[float] = 3.0

_SNAPSHOT_PATH: Final[str] = "/api/dashboard/a-share/snapshot"
_RECOMMENDATION_PATH: Final[str] = "/api/dashboard/a-share/recommendation"
_EMOTION_STATUS_PATH: Final[str] = "/api/status"
_EMOTION_ALERTS_PATH: Final[str] = "/api/alerts"


def _norm_code(code: Any) -> str | None:
    """6 位数字代码；非法 → None（调用方据此不发请求）。"""
    if code is None or isinstance(code, bool):
        return None
    s = str(code).strip()
    if not s.isdigit() or len(s) > 6:
        return None
    return s.zfill(6)


def _get_json(base: str, path: str, params: dict[str, str]) -> tuple[dict[str, Any] | None, str | None]:
    """GET → (payload, error)。**绝不抛。**"""
    url = f"{base}{path}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310 - 固定回环地址
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # noqa: BLE001 - 契约是「绝不抛」
        return None, f"{type(exc).__name__}: {exc}"
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, f"非法 JSON: {exc}"
    if not isinstance(data, dict):
        return None, f"响应不是 JSON 对象（{type(data).__name__}）"
    return data, None


def fetch_cpt_snapshot(code: str) -> tuple[dict[str, Any] | None, str | None]:
    """CPT 的 A 股快照（含 overlays：分型/笔/中枢/趋势）。"""
    norm = _norm_code(code)
    if norm is None:
        return None, "非法代码"
    return _get_json(CPT_BASE, _SNAPSHOT_PATH, {"code": norm})


def fetch_cpt_recommendation(code: str) -> tuple[dict[str, Any] | None, str | None]:
    """CPT 的结论（buy/sell/watch/hold）。"""
    norm = _norm_code(code)
    if norm is None:
        return None, "非法代码"
    return _get_json(CPT_BASE, _RECOMMENDATION_PATH, {"code": norm})


def fetch_emotion_status() -> tuple[dict[str, Any] | None, str | None]:
    """emotion-core 的整体状态（情绪阶段、buy_window 等）。"""
    return _get_json(EMOTION_BASE, _EMOTION_STATUS_PATH, {})


def fetch_emotion_alerts() -> tuple[dict[str, Any] | None, str | None]:
    """emotion-core 的告警。"""
    return _get_json(EMOTION_BASE, _EMOTION_ALERTS_PATH, {})


__all__ = (
    "CPT_BASE",
    "EMOTION_BASE",
    "TIMEOUT",
    "fetch_cpt_recommendation",
    "fetch_cpt_snapshot",
    "fetch_emotion_alerts",
    "fetch_emotion_status",
)
