"""同票并排：**三套口径**的机械对照。

## 为什么是这个形状

同一支票,三个系统各说各话：

| 来源 | 词表 | 是什么 |
|---|---|---|
| **CPT**（确定性缠论） | ``buy / sell / watch / hold`` | 缠论结构算出的买卖点 |
| **emotion 持仓决策** | ``ADD / HOLD / TRIM / EXIT`` | 情绪周期 + 资金口径的仓位建议 |
| **emotion 策略信号** | ``BUY / WATCH / PASS`` | LLM 策略（15 个 YAML）的当日信号 |

⇒ **本模块只做「并排 + 机械比对」，不做裁决。**
「以谁为准」是业务决策（见 :mod:`emotion_cpt` 的 README §3.2），
这里的职责是把差异**摆到台面上**，让裁决有依据。

## 归一维度

三套词表不同，但都能落到**看多 / 看空 / 观望**三个方向上，便于机械比对：

- 看多：CPT ``buy`` · 持仓 ``ADD`` · 策略 ``BUY``
- 看空：CPT ``sell`` · 持仓 ``EXIT``/``TRIM`` · 策略 ``PASS``
- 观望：CPT ``watch``/``hold`` · 持仓 ``HOLD`` · 策略 ``WATCH``
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .clients import (
    fetch_cpt_recommendation,
    fetch_cpt_snapshot,
    fetch_emotion_holding,
    fetch_emotion_points,
    fetch_emotion_status,
    fetch_emotion_strategy,
    norm_code,
)

#: CPT 的方向词 → 归一维度
_CPT_DIRECTION: dict[str, str] = {
    "buy": "看多",
    "sell": "看空",
    "watch": "观望",
    "hold": "观望",
}
#: emotion 持仓决策的词 → 归一维度
_HOLDING_DIRECTION: dict[str, str] = {
    "ADD": "看多",
    "TRIM": "看空",
    "EXIT": "看空",
    "HOLD": "观望",
}
#: emotion 策略信号的词 → 归一维度
_STRATEGY_DIRECTION: dict[str, str] = {
    "BUY": "看多",
    "PASS": "看空",
    "WATCH": "观望",
}

#: 归一维度 → 展示用颜色（纯展示，不含语义判断）
_DIRECTION_CLASS: dict[str, str] = {"看多": "up", "看空": "down", "观望": "flat", "未知": "none"}


def _direction(mapping: dict[str, str], raw: Any) -> str:
    if not isinstance(raw, str):
        return "未知"
    return mapping.get(raw.strip().upper() if raw.strip().upper() in mapping else raw, "未知")


def _cpt_structure(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """从 CPT 快照里抽出结构摘要（不给原始数组，那是前端的事）。"""
    if not snapshot:
        return {"available": False}
    overlays = snapshot.get("overlays") or {}
    signal = snapshot.get("signal") or {}
    quality = snapshot.get("data_quality") or {}
    return {
        "available": True,
        "counts": {
            "分型": len(overlays.get("fractals") or []),
            "笔": len(overlays.get("bis") or []),
            "中枢": len(overlays.get("zhongshus") or []),
            "走势": len(overlays.get("trend_types") or []),
        },
        "divergence_status": signal.get("divergence_status"),
        "signal_status": signal.get("status"),
        "bars": quality.get("closed_bar_count"),
        "sufficient": quality.get("sufficient"),
    }


def _strategy_for(code: str, items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """从当日策略信号里挑出该票的。"""
    out: list[dict[str, Any]] = []
    for item in items or []:
        if str(item.get("code", "")).zfill(6) != code:
            continue
        out.append(
            {
                "strategy": item.get("strategy"),
                "name": item.get("name"),
                "action": item.get("action"),
                "score": item.get("score"),
                "confidence": item.get("confidence"),
                "reason": item.get("reason"),
            }
        )
    return out


def _verdicts(
    cpt_action: Any, holding_action: Any, strategies: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """三套口径的结论并排。"""
    out: list[dict[str, Any]] = []
    cpt_dir = _direction(_CPT_DIRECTION, cpt_action)
    out.append(
        {
            "source": "CPT 确定性缠论",
            "raw": cpt_action,
            "direction": cpt_dir,
            "cls": _DIRECTION_CLASS[cpt_dir],
        }
    )
    hold_dir = _direction(_HOLDING_DIRECTION, holding_action)
    out.append(
        {
            "source": "emotion 持仓决策",
            "raw": holding_action,
            "direction": hold_dir,
            "cls": _DIRECTION_CLASS[hold_dir],
        }
    )
    if strategies:
        dirs = {_direction(_STRATEGY_DIRECTION, s.get("action")) for s in strategies}
        merged = "看多" if "看多" in dirs else ("看空" if "看空" in dirs else "观望")
        out.append(
            {
                "source": f"emotion 策略信号（{len(strategies)} 条）",
                "raw": "/".join(str(s.get("action")) for s in strategies),
                "direction": merged,
                "cls": _DIRECTION_CLASS[merged],
            }
        )
    return out


def _conflicts(
    cpt_action: Any,
    holding_action: Any,
    strategies: list[dict[str, Any]],
    levels_basis: str | None,
) -> list[dict[str, str]]:
    """机械比对：只报**事实差异**，不推断谁对。"""
    out: list[dict[str, str]] = []
    cpt_dir = _direction(_CPT_DIRECTION, cpt_action)
    hold_dir = _direction(_HOLDING_DIRECTION, holding_action)
    strat_dirs = {_direction(_STRATEGY_DIRECTION, s.get("action")) for s in strategies}

    if cpt_dir == "看多" and hold_dir not in ("看多", "未知"):
        out.append(
            {
                "kind": "buy_conflict",
                "cpt": f"CPT 判 {cpt_action}（确定性缠论）",
                "emotion": f"emotion 持仓判 {holding_action}（情绪+资金口径）",
                "note": "两套口径结论相反 —— 未裁决",
            }
        )
    if hold_dir == "看多" and cpt_dir not in ("看多", "未知"):
        out.append(
            {
                "kind": "buy_conflict",
                "cpt": f"CPT 判 {cpt_action}",
                "emotion": f"emotion 持仓判 {holding_action}",
                "note": "两套口径结论相反 —— 未裁决",
            }
        )
    if strategies and cpt_dir == "看多" and "看多" not in strat_dirs:
        out.append(
            {
                "kind": "strategy_disagree",
                "cpt": f"CPT 判 {cpt_action}",
                "emotion": "策略信号未给 BUY（"
                + "/".join(str(s.get("action")) for s in strategies)
                + "）",
                "note": "确定性缠论与 LLM 策略不同向 —— 未裁决",
            }
        )
    if levels_basis == "pct_fallback":
        out.append(
            {
                "kind": "levels_degraded",
                "cpt": "—",
                "emotion": "结构位走的是**百分比兜底**（basis=pct_fallback）",
                "note": "不是口径冲突，是**数据不完整**：结构位没算出来",
            }
        )
    return out


def build_stock_payload(code: str) -> dict[str, Any]:
    """构建同票并排 payload。任一侧不可达都不影响另一侧。"""
    norm = norm_code(code)
    if norm is None:
        return {"ok": False, "error": "非法代码（需 6 位数字）"}

    snap, snap_err = fetch_cpt_snapshot(norm)
    rec, rec_err = fetch_cpt_recommendation(norm)
    status, status_err = fetch_emotion_status()
    holding, holding_err = fetch_emotion_holding(norm)
    points, points_err = fetch_emotion_points(norm)

    # 策略信号：只在需要时拉（量大），且拉不到不影响其它
    strategies: list[dict[str, Any]] = []
    strat_err: str | None = None
    trade_date = (status or {}).get("date")
    strat_raw, strat_err = fetch_emotion_strategy(trade_date)
    if strat_raw is not None:
        strategies = _strategy_for(norm, strat_raw.get("items") or [])

    cpt_action = (rec or {}).get("action")
    levels = (points or {}).get("levels") or {}
    holding_action = (holding or {}).get("action")

    return {
        "ok": True,
        "code": norm,
        "generated_at": datetime.now(UTC).isoformat(),
        "notice": "并排展示，不做统一 —— owner 已裁决（Q1=A）："
        "三套口径各自保留，本页只做映射展示",
        "panels": {
            "cpt": {
                "available": bool(snap or rec),
                "error": snap_err or rec_err,
                "action": cpt_action,
                "action_label": (rec or {}).get("action_label"),
                "headline": (rec or {}).get("headline"),
                "reason": (rec or {}).get("reason"),
                "signal_type": (rec or {}).get("signal_type"),
                "divergence_status": (rec or {}).get("divergence_status"),
                "price_ratio": (rec or {}).get("price_ratio"),
                "structure": _cpt_structure(snap),
            },
            "emotion": {
                "available": bool(status or holding),
                "error": status_err or holding_err,
                "phase": (status or {}).get("phase"),
                "limit_up_count": (status or {}).get("limit_up_count"),
                "max_limit_days": (status or {}).get("max_limit_days"),
                "dragon_env": (status or {}).get("dragon_env"),
                "action": holding_action,
                "action_label": (holding or {}).get("action_label"),
                "market_price": ((holding or {}).get("holding") or {}).get("market_price"),
                "stop": (holding or {}).get("stop"),
                "ladder": (holding or {}).get("ladder"),
                "strategies": strategies,
                "strategy_error": strat_err,
            },
            "levels": {
                "available": points is not None,
                "error": points_err,
                "basis": levels.get("basis"),
                "buy_reference": levels.get("buy_reference"),
                "sell_reference": levels.get("sell_reference"),
                "stop_price": levels.get("stop_price"),
                "target_price": levels.get("target_price"),
                "detail": levels.get("detail"),
            },
        },
        "verdicts": _verdicts(cpt_action, holding_action, strategies),
        "conflicts": _conflicts(cpt_action, holding_action, strategies, levels.get("basis")),
    }


__all__ = ("build_stock_payload",)
