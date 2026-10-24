"""统一数据访问层 —— **本仓唯一连库的实现**。"""

from __future__ import annotations

from .config import DBCONFIG_FILE, read_dbconfig
from .connection import connect, connection_kwargs

__all__ = ("DBCONFIG_FILE", "connect", "connection_kwargs", "read_dbconfig")
