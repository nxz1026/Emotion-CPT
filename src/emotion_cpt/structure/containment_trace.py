"""Explainable containment decisions for research inspection."""

# >>> 已迁至 emotion_cpt.structure.containment_trace（2026-10-23）
# >>> 本文逐字保留，仅改写模块间 import 指向；**判据内容一字未改**。


from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from emotion_cpt.structure.contain import MergedBar
from emotion_cpt.structure.models import CanonicalBar


@dataclass(frozen=True, slots=True)
class ContainmentDecision:
    source_bar_index: int
    target_source_indices: tuple[int, ...]
    direction: Literal["forward", "backward"]
    decision: Literal["contained", "merged"]
    resulting_high: float
    resulting_low: float


def trace_containment(
    bars: tuple[CanonicalBar, ...],
    merged_bars: tuple[MergedBar, ...],
    *,
    direction: Literal["forward", "backward"] = "forward",
) -> tuple[ContainmentDecision, ...]:
    """Create deterministic source-to-merged-bar explanations."""
    traces: list[ContainmentDecision] = []
    for merged in merged_bars:
        indices = tuple(merged.source_indices)
        if len(indices) < 2:
            continue
        for index in indices[1:]:
            source = bars[index]
            previous = bars[index - 1]
            contained = (source.high <= previous.high and source.low >= previous.low) or (
                source.high >= previous.high and source.low <= previous.low
            )
            traces.append(
                ContainmentDecision(
                    source_bar_index=index,
                    target_source_indices=indices,
                    direction=direction,
                    decision="contained" if contained else "merged",
                    resulting_high=merged.high,
                    resulting_low=merged.low,
                )
            )
    return tuple(traces)
