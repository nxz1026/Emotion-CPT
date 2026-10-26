"""``~/.dbconfig`` 解析。

⚠️ 口径必须与上游两个仓**完全一致**，否则连不上：

- 文件是**字面量 ``$KEY=value`` 行**，**不是 shell 脚本** —— ``source`` 不生效
  （``$RDSHOST=...`` 在 shell 里会被当成命令名，source 会静默失败）
- 只认以 ``$`` 开头且含 ``=`` 的行；其余（注释、空行）静默跳过
- 键值两侧空白一律 strip
"""

from __future__ import annotations

import pathlib
from typing import Final

#: 凭据文件位置。**不得**把内容写进仓。
DBCONFIG_FILE: Final[pathlib.Path] = pathlib.Path.home() / ".dbconfig"

KEY_HOST: Final[str] = "$RDSHOST"
KEY_PASSWORD: Final[str] = "$DB_PW"
KEY_DBNAME: Final[str] = "$DBNAME"

DEFAULT_DBNAME: Final[str] = "emotion_core"
DEFAULT_USER: Final[str] = "postgres"
DEFAULT_PORT: Final[int] = 5432
DEFAULT_SSLMODE: Final[str] = "prefer"


def read_dbconfig(path: pathlib.Path | None = None) -> dict[str, str]:
    """解析 ``~/.dbconfig`` → ``{"$RDSHOST": "...", ...}``。

    文件不存在返回空 dict（不抛）—— 让"没配凭据"和"配错了"是两件可分辨的事。
    """
    target = path or DBCONFIG_FILE
    if not target.exists():
        return {}
    out: dict[str, str] = {}
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("$") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


__all__ = (
    "DBCONFIG_FILE",
    "DEFAULT_DBNAME",
    "DEFAULT_PORT",
    "DEFAULT_SSLMODE",
    "DEFAULT_USER",
    "KEY_DBNAME",
    "KEY_HOST",
    "KEY_PASSWORD",
    "read_dbconfig",
)
