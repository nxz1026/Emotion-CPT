"""聚合页 payload 构建 —— **并排展示两套口径，不裁决**。

⚠️ 页面顶部必须显式标注「并排展示，未裁决」。这是本仓的边界：
裁决「以谁为准」是业务决策（见 IMPLEMENTATION.md §10），不是工程能单方面定的。

「打架」的判定只做**机械比对**，不引入任何新口径：
- CPT 的 ``action`` ∈ {buy, sell, watch, hold}
- emotion 的 ``buy_window``（可能是 NONE）与情绪 ``phase``
⇒ 只报告「CPT 说买、emotion 说禁买」这类**事实差异**，不推断谁对。
"""

from __future__ import annotations

from typing import Any

from .clients import (
    fetch_cpt_recommendation,
    fetch_cpt_snapshot,
    fetch_emotion_status,
)

#: CPT 侧的动作词表（与 cpt/domain/signal.py 的契约）
CPT_ACTIONS = ("buy", "sell", "watch", "hold")


def build_stock_payload(code: str) -> dict[str, Any]:
    """构建同票并排 payload。任一侧不可达都不影响另一侧。"""
    snap, snap_err = fetch_cpt_snapshot(code)
    rec, rec_err = fetch_cpt_recommendation(code)
    status, status_err = fetch_emotion_status()

    cpt_action = (rec or {}).get("action")
    cpt_view = {
        "available": snap is not None or rec is not None,
        "error": snap_err or rec_err,
        "action": cpt_action,
        "action_label": (rec or {}).get("action_label"),
        "headline": (rec or {}).get("headline"),
        "reason": (rec or {}).get("reason"),
        "price": (rec or {}).get("price"),
        "status": (rec or {}).get("status"),
        "signal_type": (rec or {}).get("signal_type"),
        "divergence_status": (rec or {}).get("divergence_status"),
        "data_quality": (snap or {}).get("data_quality"),
        "overlays": (snap or {}).get("overlays"),
    }

    emotion_view = {
        "available": status is not None,
        "error": status_err,
        "phase": (status or {}).get("phase"),
        "buy_window": (status or {}).get("buy_window"),
        "force_liquidate": (status or {}).get("force_liquidate"),
        "dragon_env": (status or {}).get("dragon_env"),
    }

    return {
        "code": code,
        "notice": "并排展示，未裁决 —— 两套口径的差异由 owner 裁定",
        "cpt": cpt_view,
        "emotion": emotion_view,
        "conflicts": detect_conflicts(cpt_view, emotion_view),
    }


def detect_conflicts(cpt: dict[str, Any], emotion: dict[str, Any]) -> list[dict[str, str]]:
    """机械比对两套口径，**只报告事实差异**。"""
    out: list[dict[str, str]] = []
    cpt_action = cpt.get("action")
    buy_window = emotion.get("buy_window")

    if cpt_action == "buy" and isinstance(buy_window, str) and buy_window.upper() == "NONE":
        out.append(
            {
                "kind": "buy_conflict",
                "cpt": "CPT 判 buy（确定性缠论）",
                "emotion": f"emotion 判 buy_window={buy_window}（情绪口径禁买）",
                "note": "两边并排展示，未裁决",
            }
        )
    if cpt_action in ("buy", "sell") and not cpt.get("available"):
        out.append({"kind": "cpt_unavailable", "cpt": "CPT 侧不可用", "emotion": "-", "note": "-"})
    if cpt_action is not None and cpt_action not in CPT_ACTIONS:
        out.append(
            {
                "kind": "vocabulary",
                "cpt": f"未知的 action 取值 {cpt_action!r}",
                "emotion": "-",
                "note": "词表可能已漂移，请核对契约",
            }
        )
    return out


__all__ = ("CPT_ACTIONS", "build_stock_payload", "detect_conflicts")
