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
        ("GET", "/api/v1/runs/any-run/decisions"),
        ("GET", "/api/v1/runs/any-run/trades"),
        ("GET", "/api/v1/runs/any-run/trades/markers"),
        ("GET", "/api/v1/runs/any-run/ohlcv?timeframe=1m"),
        ("GET", "/api/v1/runs/any-run/metrics"),
        ("GET", "/api/v1/runs/any-run/timeline"),
        ("GET", "/api/v1/runs/any-run/errors"),
        ("GET", "/api/v1/runs/any-run/decisions/export?format=json"),
        ("GET", "/api/v1/runs/any-run/errors/export?format=json"),
        ("GET", "/api/v1/runs/any-run/trades/export?format=json"),
    ],
)
@pytest.mark.parametrize(
    ("scenario", "expected_code"),
    [
        ("UNSET", "RUNS_ROOT_UNSET"),
        ("MISSING", "RUNS_ROOT_MISSING"),
        ("INVALID", "RUNS_ROOT_INVALID"),
        ("NOT_WRITABLE", "RUNS_ROOT_NOT_WRITABLE"),
    ],
)
def test_runs_root_misconfig_contract_across_run_endpoints(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    method: str,
    path: str,
    scenario: str,
    expected_code: str,
) -> None:
    monkeypatch.delenv("DEMO_MODE", raising=False)
    if scenario == "UNSET":
        monkeypatch.delenv("RUNS_ROOT", raising=False)
    elif scenario == "MISSING":
        missing = tmp_path / "runs_missing"
        monkeypatch.setenv("RUNS_ROOT", str(missing))
    elif scenario == "INVALID":
        root_file = tmp_path / "runs_root.txt"
        root_file.write_text("not a directory", encoding="utf-8")
        monkeypatch.setenv("RUNS_ROOT", str(root_file))
    elif scenario == "NOT_WRITABLE":
        runs_root = tmp_path / "runs"
        runs_root.mkdir()
        monkeypatch.setenv("RUNS_ROOT", str(runs_root))
        monkeypatch.setattr(
            "apps.api.main._check_runs_root_writable",
            lambda _path: (False, "blocked"),
        )
        monkeypatch.setattr(
            "apps.api.phase6.run_builder._check_runs_root_writable",
            lambda _path: (False, "blocked"),
        )
    else:
        raise AssertionError(f"unknown scenario: {scenario}")

    client = TestClient(app)

    if method == "POST":
        response = client.post(path, json=_valid_run_payload())
    else:
        response = client.get(path)

    _assert_canonical_runs_root_error(response, expected_code)
