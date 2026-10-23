"""探针输出必须稳定（指纹算法变更 = 破坏性变更）。"""

from __future__ import annotations

from emotion_cpt.db.probe import contract_payload, fingerprint


def test_payload_shape():
    payload = contract_payload()
    assert payload["version"] == 1
    assert len(payload["tables"]) == 52
    assert len(payload["intraday_seal"]["columns"]) == 9
    assert set(payload["pricing"]) == {
        "BUY_BUFFER", "SELL_BUFFER", "STOP_LOSS_RATIO", "BI_LOOKBACK", "ZHONGSHU_LOOKBACK",
    }


def test_fingerprint_is_stable():
    assert fingerprint() == fingerprint()
    assert len(fingerprint()) == 16


def test_payload_contains_no_credentials():
    blob = str(contract_payload()).lower()
    for secret in ("password", "api_key", "rdshost", "db_pw"):
        assert secret not in blob
