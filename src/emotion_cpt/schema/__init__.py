"""schema 真相源 —— 描述「谁拥有什么」，不执行迁移。"""

from __future__ import annotations

from .manifest import load_manifest, manifest_fingerprint

__all__ = ("load_manifest", "manifest_fingerprint")
