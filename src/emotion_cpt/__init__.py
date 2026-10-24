"""Emotion-CPT —— CPT × emotion-core 的统一层。

**本包不实现任何业务逻辑。** 它只持有：
跨项目契约（表归属 / 列定义 / 常量）、统一数据层、统一 web 入口、部署真相源。

依赖方向是**单向**的：上游（``cpt`` / ``emotion_core``）可以依赖本仓的契约包；
本仓**不得**依赖上游 —— 门禁会强制这条方向。
"""

from __future__ import annotations

#: 版本号**从已安装的包元数据读**，不写死。
#:
#: ⚠️ 写死会自己漂：2026-10-24 就出现过 ``__version__`` 还写着 0.1.0、
#: 而包元数据已经是 0.2.0（改了 pyproject 的 version 但没改这里）——
#: **同一个仓里两个版本号**，而整个项目存在的意义就是消灭这种事。
#:
#: 读不到的场合（直接从源码树跑、没装成包）⇒ 退到一个明确的 dev 标记，
#: 绝不假装自己是某个正式版本。
try:  # pragma: no cover - 环境相关
    from importlib.metadata import PackageNotFoundError, version

    try:
        __version__ = version("emotion-cpt")
    except PackageNotFoundError:
        __version__ = "0.0.0+not-installed"
except Exception:  # pragma: no cover
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
