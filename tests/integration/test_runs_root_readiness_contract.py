from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app


def _valid_run_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "data_source": {
            "type": "csv",
            "path": "tests/fixtures/phase6/sample.csv",
            "symbol": "BTCUSDT",
            "timeframe": "1m",
        },
        "strategy": {"id": "hold"},
        "risk": {"level": 3},
        "costs": {"commission_bps": 0, "slippage_bps": 0},
    }


def _assert_canonical_runs_root_error(response, expected_code: str) -> None:
    assert response.status_code == 503
    payload = response.json()
    for key in ("code", "message", "details", "error"):
        assert key in payload
    assert payload["code"] == expected_code
    assert isinstance(payload["message"], str) and payload["message"].strip()
    assert isinstance(payload["details"], dict)
    error = payload["error"]
    assert isinstance(error, dict)
    assert error["code"] == expected_code
    assert error["message"] == payload["message"]
    assert error["details"] == payload["details"]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/ready"),
        ("GET", "/api/v1/runs"),
        ("POST", "/api/v1/runs"),
        ("GET", "/api/v1/runs/any-run/manifest"),
        ("GET", "/api/v1/runs/any-run/artifacts/manifest.json"),
        ("GET", "/api/v1/runs/any-run/summary"),
    ],
)
def test_runs_root_unset_contract_across_run_endpoints(
    monkeypatch: pytest.MonkeyPatch, method: str, path: str
) -> None:
    monkeypatch.delenv("RUNS_ROOT", raising=False)
    monkeypatch.delenv("DEMO_MODE", raising=False)
    client = TestClient(app)

    if method == "POST":
        response = client.post(path, json=_valid_run_payload())
    else:
        response = client.get(path)

    _assert_canonical_runs_root_error(response, "RUNS_ROOT_UNSET")
