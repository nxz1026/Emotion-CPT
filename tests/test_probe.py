"""探针输出必须稳定（指纹算法变更 = 破坏性变更）。"""

from __future__ import annotations

from emotion_cpt.contracts import pricing
from emotion_cpt.db.probe import contract_payload, fingerprint


def test_payload_shape():
    payload = contract_payload()
    assert payload["version"] == 1
    assert len(payload["tables"]) == 47
    assert len(payload["intraday_seal"]["columns"]) == 9
    # 每列的 semantics 也要在指纹里
    assert all(c["semantics"] for c in payload["intraday_seal"]["columns"])
    # ⚠️ 断言的是**模块里实际存在的全部常量**（内省出来的），
    # 不是手写清单 —— 手写清单正是当初漏掉 PRICE_ROUND_DIGITS 的原因。
    assert set(payload["pricing"]) == {
        n for n in dir(pricing) if n.isupper() and not n.startswith("_")
    }
    assert "PRICE_ROUND_DIGITS" in payload["pricing"]


def test_fingerprint_is_stable():
    assert fingerprint() == fingerprint()
    assert len(fingerprint()) == 16


def test_payload_contains_no_credentials():
    blob = str(contract_payload()).lower()
    for secret in ("password", "api_key", "rdshost", "db_pw"):
        assert secret not in blob
