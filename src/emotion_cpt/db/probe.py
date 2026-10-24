"""只读探针 —— 产出**契约指纹**，供上游 CI 校验。

⚠️ 输出只含指纹与表名，**不含任何业务数据、不含凭据**。
指纹算法变更 = 破坏性变更（上游要跟着改校验逻辑）。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from emotion_cpt.contracts import pricing
from emotion_cpt.contracts.intraday_seal import INTRADAY_SEAL_COLUMNS, INTRADAY_SEAL_TABLE
from emotion_cpt.contracts.shared_tables import SHARED_TABLES
from emotion_cpt.contracts.tables import TABLES


def contract_payload() -> dict[str, Any]:
    """契约的机器可读快照。"""
    return {
        "version": 1,
        "tables": [
            {"name": t.name, "owner": t.owner, "writer": t.writer, "readers": list(t.readers),
             "legacy": t.legacy}
            for t in TABLES
        ],
        "shared_tables": [
            {"name": t.name, "date_column": t.date_column, "writer": t.writer}
            for t in SHARED_TABLES
        ],
        "intraday_seal": {
            "table": INTRADAY_SEAL_TABLE,
            "columns": [
                {
                    "name": c.name,
                    "dtype": c.dtype,
                    "nullable": c.nullable,
                    "unit": c.unit,
                    # ⚠️ `semantics` 也要进指纹 —— 「同名不同义」是最贵的漂移
                    #   （`bid1_lots` 是手不是股），不带它指纹就看不见
                    "semantics": c.semantics,
                }
                for c in INTRADAY_SEAL_COLUMNS
            ],
        },
        # ⚠️ **从模块内省**，不要手写常量清单 ——
        #   手写过一次，漏了 P3 加的 `PRICE_ROUND_DIGITS`（指纹里根本没有它）。
        #   内省 ⇒ 新增常量自动进指纹，**结构上不可能再漏**。
        "pricing": {
            name: getattr(pricing, name)
            for name in sorted(dir(pricing))
            if name.isupper() and not name.startswith("_")
        },
    }


def fingerprint(payload: dict[str, Any] | None = None) -> str:
    """契约指纹（sha256 前 16 位）。"""
    data = payload if payload is not None else contract_payload()
    blob = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def dump() -> str:
    """给上游 CI 用的 JSON 输出。"""
    return json.dumps(
        {"fingerprint": fingerprint(), "contract": contract_payload()},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


__all__ = ("contract_payload", "dump", "fingerprint")
