"""Emotion-CPT —— CPT × emotion-core 的统一层。

**本包不实现任何业务逻辑。** 它只持有：
跨项目契约（表归属 / 列定义 / 常量）、统一数据层、统一 web 入口、部署真相源。

依赖方向是**单向**的：上游（``cpt`` / ``emotion_core``）可以依赖本仓的契约包；
本仓**不得**依赖上游 —— 门禁会强制这条方向。
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
