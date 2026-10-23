"""表 manifest 的加载与指纹。"""

from __future__ import annotations

from typing import Any

from emotion_cpt.contracts.tables import TABLES, TableSpec


def load_manifest() -> tuple[TableSpec, ...]:
    """返回全部表声明。"""
    return TABLES


def manifest_fingerprint() -> str:
    """manifest 指纹（供门禁比对）。"""
    from emotion_cpt.db.probe import fingerprint

    return fingerprint()


def summary() -> dict[str, Any]:
    """按归属方汇总。"""
    out: dict[str, dict[str, int]] = {}
    for spec in TABLES:
        bucket = out.setdefault(spec.owner, {"total": 0, "legacy": 0})
        bucket["total"] += 1
        if spec.legacy:
            bucket["legacy"] += 1
    return out


__all__ = ("load_manifest", "manifest_fingerprint", "summary")
