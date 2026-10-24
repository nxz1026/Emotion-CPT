"""对两个上游的**只读** HTTP 客户端。

**硬约束**（逐条抄自上游 ``emotion_core/services/cpt_client.py`` 的设计要求，
因为那些约束是被真实事故打出来的）：

1. 只用标准库 ``urllib.request``
2. **绝不抛** —— 任何失败返回 ``None`` + 结构化的「不可用原因」
   （CPT 挂了也必须能出结果，走降级）
3. **只允许回环** —— host 由模块常量拼，**不接受调用方传 host**
4. **只调读端点** —— 本门面不写任何数据
5. 不缓存 —— 快照随行情变

三个上游各司其职：

- **CPT**（:8010）—— 确定性缠论：结构（分型/笔/中枢/趋势）、买卖点结论
- **emotion-core**（:8098）—— 情绪周期：阶段、情绪持仓决策、策略信号
- **emotion-core 的 ``/api/cpt/points``** —— 它自己算出的**结构位**
  （经由本门面 → CPT → emotion 的链路，本门面只做转发与并排）
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

#: 回环请求超时上限。慢就是不正常。
TIMEOUT: Final[float] = 3.0
#: 情绪侧的持仓决策要拉因子/算结构位，给更宽的窗口
TIMEOUT_SLOW: Final[float] = 30.0

_SNAPSHOT_PATH: Final[str] = "/api/dashboard/a-share/snapshot"
_RECOMMENDATION_PATH: Final[str] = "/api/dashboard/a-share/recommendation"
_EMO_STATUS_PATH: Final[str] = "/api/status"
_EMO_HOLDING_PATH: Final[str] = "/api/holding"
_EMO_STRATEGY_PATH: Final[str] = "/api/strategy"
_EMO_POINTS_PATH: Final[str] = "/api/cpt/points"


def norm_code(code: Any) -> str | None:
    """6 位数字代码；非法 → None（调用方据此不发请求）。"""
    if code is None or isinstance(code, bool):
        return None
    s = str(code).strip()
    if not s.isdigit() or len(s) > 6:
        return None
    return s.zfill(6)


def get_json(
    base: str, path: str, params: dict[str, str] | None = None, *, timeout: float = TIMEOUT
) -> tuple[dict[str, Any] | None, str | None]:
    """GET → ``(payload, error)``。**绝不抛。**

    :returns: ``(dict, None)`` 成功；``(None, "原因")`` 失败
    """
    query = urllib.parse.urlencode(params or {})
    url = f"{base}{path}" + (f"?{query}" if query else "")
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - 固定回环
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


# ────────────────────────── CPT（确定性缠论） ──────────────────────────


def fetch_cpt_snapshot(code: str) -> tuple[dict[str, Any] | None, str | None]:
    """CPT 的 A 股快照：结构（overlays）+ 信号 + 数据质量。"""
    norm = norm_code(code)
    if norm is None:
        return None, "非法代码"
    return get_json(CPT_BASE, _SNAPSHOT_PATH, {"code": norm}, timeout=TIMEOUT_SLOW)


def fetch_cpt_recommendation(code: str) -> tuple[dict[str, Any] | None, str | None]:
    """CPT 的结论：action（buy/sell/watch/hold）+ headline + reason。"""
    norm = norm_code(code)
    if norm is None:
        return None, "非法代码"
    return get_json(CPT_BASE, _RECOMMENDATION_PATH, {"code": norm}, timeout=TIMEOUT_SLOW)


# ────────────────────── emotion-core（情绪周期） ──────────────────────


def fetch_emotion_status() -> tuple[dict[str, Any] | None, str | None]:
    """情绪市场状态：阶段（退潮/…/高潮）、连板高度、龙头环境。"""
    return get_json(EMOTION_BASE, _EMO_STATUS_PATH, {}, timeout=TIMEOUT)


def fetch_emotion_holding(code: str) -> tuple[dict[str, Any] | None, str | None]:
    """emotion-core 对该票的**持仓决策**（它自己的口径，与 CPT 无关）。

    慢：它可能触发结构位计算（拉因子）。
    """
    norm = norm_code(code)
    if norm is None:
        return None, "非法代码"
    return get_json(EMOTION_BASE, _EMO_HOLDING_PATH, {"code": norm}, timeout=TIMEOUT_SLOW)


def fetch_emotion_points(code: str) -> tuple[dict[str, Any] | None, str | None]:
    """emotion-core 算出的**结构位**（买/卖/止损 + basis）。

    注意：它的 levels 来自 CPT 的 overlays，但**取整与兜底是 emotion 自己的口径**。
    """
    norm = norm_code(code)
    if norm is None:
        return None, "非法代码"
    return get_json(EMOTION_BASE, _EMO_POINTS_PATH, {"code": norm}, timeout=TIMEOUT_SLOW)


def fetch_emotion_strategy(date: str | None = None) -> tuple[dict[str, Any] | None, str | None]:
    """某交易日的策略信号（BUY/WATCH/PASS）。

    数据量大（每天几千条）⇒ 只在需要时拉，且由调用方按 code 过滤。
    """
    params = {"date": date} if date else {}
    return get_json(EMOTION_BASE, _EMO_STRATEGY_PATH, params, timeout=TIMEOUT_SLOW)


__all__ = (
    "CPT_BASE",
    "EMOTION_BASE",
    "TIMEOUT",
    "TIMEOUT_SLOW",
    "fetch_cpt_recommendation",
    "fetch_cpt_snapshot",
    "fetch_emotion_holding",
    "fetch_emotion_points",
    "fetch_emotion_status",
    "fetch_emotion_strategy",
    "get_json",
    "norm_code",
)
