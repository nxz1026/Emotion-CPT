"""Emotion-CPT —— CPT × emotion-core 的统一层。

**本包不实现任何业务逻辑。** 它只持有：
跨项目契约（表归属 / 列定义 / 常量）、统一数据层、统一 web 入口、部署真相源。

依赖方向是**单向**的：上游（``cpt`` / ``emotion_core``）可以依赖本仓的契约包；
本仓**不得**依赖上游 —— 门禁会强制这条方向。
"""

from __future__ import annotations

import re
from pathlib import Path

#: 版本号**优先从源码树的 pyproject 读**，其次才用已安装的包元数据。
#:
#: ⚠️ 写死会自己漂：2026-10-24 就出现过 ``__version__`` 还写着 0.1.0、
#: 而包元数据已经是 0.2.0（改了 pyproject 的 version 但没改这里）——
#: **同一个仓里两个版本号**，而整个项目存在的意义就是消灭这种事。
#:
#: ⚠️ 2026-10-25（真机）：**只读元数据也不够** ——
#: 源码树里躺着一份**陈旧的** ``src/emotion_cpt.egg-info/``（构建产物，gitignore 掉的），
#: 它的 PKG-INFO 还写着旧版本（0.8.3）⇒ 跑在 ``PYTHONPATH=src`` 下时
#: ``importlib.metadata.version("emotion-cpt")`` **优先命中它**（而不是 venv 里的
#: dist-info）⇒ ``__version__`` 变成 0.8.3 ⇒ 门禁 ``test_version_single_source`` 红。
#: ⇒ 上一轮「订正 dist-info」订正的是**影子**（被 egg-info 遮住了），
#: **本体**（egg-info）没人动。
#:
#: ⇒ 铁律（本仓一直这么要求的）：
#: **源码树里读 pyproject 优先，装成包时读元数据兜底。**
#: 这样任何**陈旧的构建产物**都影响不到版本号。
#:
#: 读不到的场合（既没有 pyproject、也没装成包）⇒ 退到一个明确的 dev 标记，
#: 绝不假装自己是某个正式版本。
_PACKAGE_NAME = "emotion-cpt"


def _version_from_pyproject() -> str | None:
    """从**本包所属仓**的 pyproject.toml 读 version（读不到就返回 None）。

    只认 ``name = "emotion-cpt"`` 的 pyproject ⇒ 不会误读上层目录里别的项目的版本。
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        pyproject = parent / "pyproject.toml"
        if not pyproject.is_file():
            continue
        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError:
            return None
        if not re.search(rf'(?m)^\s*name\s*=\s*"{re.escape(_PACKAGE_NAME)}"', text):
            return None
        m = re.search(r'(?m)^\s*version\s*=\s*"([^"]+)"', text)
        if m:
            return m.group(1)
        return None
    return None


def _version_from_metadata() -> str | None:
    """已安装的包元数据（装成包时用；读不到返回 None）。"""
    try:
        from importlib.metadata import PackageNotFoundError, version
    except Exception:  # pragma: no cover - 极老环境
        return None
    try:
        return version(_PACKAGE_NAME)
    except PackageNotFoundError:
        return None
    except Exception:  # pragma: no cover
        return None


#: 优先级：源码树的 pyproject > 已安装的包元数据 > 明确的 dev 标记
__version__: str = (
    _version_from_pyproject() or _version_from_metadata() or "0.0.0+not-installed"
)

__all__ = ["__version__"]
