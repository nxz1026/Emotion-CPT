"""★ 契约门禁的**自证**：注入假数据 ⇒ 门禁必须报错。

纪律来源：上游 R45 —— *「自制的验证工具第一版基本都错」*。
**跑全绿不够，必须注入假数据确认它还能报。**

（本文件 2026-10-24 补：门禁改判据后，绿色的那次其实是**假绿** ——
它扫不到 P3 之后「从契约包 import」的写法，于是对真实仓库报「常量未找到」。
⇒ 这就是为什么门禁必须有自证用例。）

这里用**合成的小仓**（不拷真实仓，避免把磁盘塞满）：

- ``cpt/application/track_points.py``  —— 价格常量从契约包 import
- ``cpt/storage/intraday_seal_store.py`` —— 9 列清单（写在两个常量里）
- ``src/emotion_core/algorithms/levels.py`` —— 同样从契约包 import
- ``src/emotion_core/data/providers/cpt_intraday.py`` —— 9 列清单（元组）
"""

from __future__ import annotations

from pathlib import Path

import pytest

from emotion_cpt.cli import check_contracts

#: 契约里的 9 列（与 contracts.intraday_seal 一致）
COLUMNS = (
    "at",
    "code",
    "sealed",
    "bid1_lots",
    "limit_price",
    "price",
    "prev_close",
    "distance_pct",
    "is_st",
)

_PRICE_SRC = '''"""合成上游：从契约包 import 价格常量。"""

from __future__ import annotations

from typing import Any, Final

from emotion_cpt.contracts.pricing import (
    BUY_BUFFER,
    SELL_BUFFER,
    STOP_LOSS_RATIO,
)

__all__ = ("BUY_BUFFER", "SELL_BUFFER", "STOP_LOSS_RATIO")
'''

_SEAL_STORE_SRC = '''"""合成的封板快照写入侧。"""

from __future__ import annotations

from typing import Final

_SELECT_COLS: Final[str] = (
    "at, code, sealed, bid1_lots, limit_price, price, prev_close, distance_pct, is_st"
)

_INSERT_SQL: Final[str] = (
    "INSERT INTO public.intraday_seal_snapshot ("
    "at, code, sealed, bid1_lots, limit_price, price, prev_close, distance_pct, is_st) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
    "ON CONFLICT (at, code) DO NOTHING"
)
'''

_SEAL_READER_SRC = '''"""合成的封板快照读取侧。"""

from __future__ import annotations

from typing import Final

_COLUMNS: Final[tuple[str, ...]] = (
    "at",
    "code",
    "sealed",
    "bid1_lots",
    "limit_price",
    "price",
    "prev_close",
    "distance_pct",
    "is_st",
)
'''


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_upstream(root: Path) -> Path:
    """造一个「像上游」的最小仓树。"""
    _write(root / "cpt" / "application" / "track_points.py", _PRICE_SRC)
    _write(root / "cpt" / "storage" / "intraday_seal_store.py", _SEAL_STORE_SRC)
    _write(root / "src" / "emotion_core" / "algorithms" / "levels.py", _PRICE_SRC)
    _write(
        root / "src" / "emotion_core" / "data" / "providers" / "cpt_intraday.py",
        _SEAL_READER_SRC,
    )
    return root


def _run(root: Path) -> list[check_contracts.Issue]:
    upstreams = check_contracts.detect_upstreams(root)
    issues: list[check_contracts.Issue] = []
    issues += check_contracts.check_constant_sources(upstreams)
    issues += check_contracts.check_contract_values(upstreams)
    issues += check_contracts.check_seal_columns(upstreams)
    return issues


def test_detect_upstreams_finds_both(tmp_path: Path):
    root = _make_upstream(tmp_path)
    found = check_contracts.detect_upstreams(root)
    assert set(found) == {"cpt", "emotion-core"}


def test_detect_upstreams_returns_empty_for_foreign_dir(tmp_path: Path):
    assert check_contracts.detect_upstreams(tmp_path) == {}


def test_clean_tree_passes(tmp_path: Path):
    root = _make_upstream(tmp_path)
    assert _run(root) == []


def test_handwritten_constant_is_caught(tmp_path: Path):
    """★ 有人又手抄了一份常量 ⇒ 必须报红。"""
    root = _make_upstream(tmp_path)
    target = root / "src" / "emotion_core" / "algorithms" / "levels.py"
    target.write_text(
        target.read_text(encoding="utf-8") + "\nBUY_BUFFER: Final[float] = 1.03\n",
        encoding="utf-8",
    )
    issues = _run(root)
    assert any(i.kind == "handwritten" for i in issues)


def test_seal_column_drift_is_caught(tmp_path: Path):
    """★ 9 列被改 ⇒ 必须报红（写入侧与读取侧都要抓到）。"""
    root = _make_upstream(tmp_path)
    store = root / "cpt" / "storage" / "intraday_seal_store.py"
    store.write_text(
        store.read_text(encoding="utf-8").replace("is_st", "is_st_x"), encoding="utf-8"
    )
    issues = _run(root)
    assert any(i.kind == "drift" and "cpt/" in i.where for i in issues)


def test_reader_side_column_drift_is_caught(tmp_path: Path):
    root = _make_upstream(tmp_path)
    reader = root / "src" / "emotion_core" / "data" / "providers" / "cpt_intraday.py"
    reader.write_text(
        reader.read_text(encoding="utf-8").replace('"bid1_lots",', '"bid1_lots_x",'),
        encoding="utf-8",
    )
    issues = _run(root)
    assert any(i.kind == "drift" and "emotion-core/" in i.where for i in issues)


def test_unparsable_source_is_reported_not_crashed(tmp_path: Path):
    """★ 源码语法坏掉 ⇒ 门禁要报错，不能自己崩。"""
    root = _make_upstream(tmp_path)
    target = root / "src" / "emotion_core" / "algorithms" / "levels.py"
    target.write_text(target.read_text(encoding="utf-8") + "\nnot python(((\n", encoding="utf-8")
    issues = _run(root)
    assert any(i.kind == "unparsable" for i in issues)


def test_stale_pin_is_caught(tmp_path: Path):
    """★ 上游 pin 的契约版本落后 ⇒ 必须报红。"""
    root = _make_upstream(tmp_path)
    _write(
        root / "pyproject.toml",
        '[project]\nname = "x"\nversion = "0.1.0"\n'
        'dependencies = ["emotion-cpt @ git+https://github.com/nxz1026/Emotion-CPT.git@v0.0.1"]\n',
    )
    upstreams = check_contracts.detect_upstreams(root)
    issues = check_contracts.check_pinned_versions(upstreams)
    assert any(i.kind == "stale-pin" for i in issues)


def test_version_normalisation():
    """``v0.1.0`` 与 ``0.1.0`` 是同一个东西。"""
    assert check_contracts._norm_version("v0.1.0") == check_contracts._norm_version("0.1.0")
    assert check_contracts._norm_version("v0.1.0") != check_contracts._norm_version("v0.0.1")


def test_version_single_source():
    """★ 版本号只有一个来源：包元数据。

    2026-10-24 出现过 ``__version__`` 写死 0.1.0、而 pyproject 已是 0.2.0
    ⇒ 同一个仓里两个版本号。整个项目存在的意义就是消灭这种事，自己不能犯。
    """
    import emotion_cpt

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    if not pyproject.exists():
        pytest.skip("源码树里没有 pyproject.toml（未以仓根运行）")
    import re

    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"))
    assert m, "pyproject.toml 里没有 version"
    try:
        from importlib.metadata import version

        installed = version("emotion-cpt")
    except Exception:  # noqa: BLE001
        pytest.skip("本仓未以包形式安装")
    assert emotion_cpt.__version__ == installed == m.group(1)
