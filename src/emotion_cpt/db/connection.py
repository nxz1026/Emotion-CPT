"""psycopg 连接参数 —— 与上游同口径，但**只此一份**。"""

from __future__ import annotations

import pathlib
from typing import Any

from .config import (
    DEFAULT_DBNAME,
    DEFAULT_PORT,
    DEFAULT_SSLMODE,
    DEFAULT_USER,
    KEY_DBNAME,
    KEY_HOST,
    KEY_PASSWORD,
    read_dbconfig,
)


class DbConfigError(RuntimeError):
    """``~/.dbconfig`` 不可读或缺必需键。"""


def connection_kwargs(path: pathlib.Path | None = None) -> dict[str, Any]:
    """构造 psycopg 连接参数。

    :raises DbConfigError: 凭据缺失（**不打印凭据内容**）。
    """
    cfg = read_dbconfig(path)
    host = cfg.get(KEY_HOST, "")
    password = cfg.get(KEY_PASSWORD, "")
    if not host or not password:
        raise DbConfigError(
            f"凭据缺失：需要 {KEY_HOST} 与 {KEY_PASSWORD}（来源 ~/.dbconfig，格式 $KEY=value）"
        )
    return {
        "host": host,
        "port": DEFAULT_PORT,
        "dbname": cfg.get(KEY_DBNAME, DEFAULT_DBNAME),
        "user": DEFAULT_USER,
        "password": password,
        "sslmode": DEFAULT_SSLMODE,
        # 链路防挂死：握手上限 + TCP keepalive 探活
        "connect_timeout": 15,
        "keepalives": 1,
        "keepalives_idle": 20,
        "keepalives_interval": 10,
        "keepalives_count": 3,
    }


def connect(path: pathlib.Path | None = None) -> Any:
    """建立连接。psycopg 是**可选依赖**（``pip install "emotion-cpt[db]"``）。"""
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - 依赖缺失时的友好提示
        raise DbConfigError('缺 psycopg：pip install "emotion-cpt[db]"') from exc
    return psycopg.connect(**connection_kwargs(path))


__all__ = ("DbConfigError", "connect", "connection_kwargs")
