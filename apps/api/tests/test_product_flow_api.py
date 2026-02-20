from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app

TEST_USER_ID = "test-user"
SAMPLE_CSV = Path("tests/fixtures/phase6/sample.csv")


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[TestClient, Path]:
    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("BUFF_DEFAULT_USER", TEST_USER_ID)
    client = TestClient(app)
    try:
        yield client, runs_root
    finally:
        client.close()


def _import_dataset(client: TestClient, csv_bytes: bytes) -> dict[str, object]:
    response = client.post(
        "/api/v1/data/import",
        files={"file": ("sample.csv", csv_bytes, "text/csv")},
    )
    assert response.status_code == 201
    payload = response.json()
    assert isinstance(payload, dict)
    return payload


def test_strategies_catalog_non_empty_and_stable(api_client: tuple[TestClient, Path]) -> None:
    client, _ = api_client
    first = client.get("/api/v1/strategies")
    second = client.get("/api/v1/strategies")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()

    rows = first.json()
    assert isinstance(rows, list)
    assert rows
    for row in rows:
        assert row["id"]
        assert row["display_name"]
        assert row["description"]
        assert isinstance(row["param_schema"], dict)
        assert isinstance(row["default_params"], dict)
        assert isinstance(row["tags"], list)


def test_data_import_produces_content_hash_manifest(api_client: tuple[TestClient, Path]) -> None:
    client, runs_root = api_client
    csv_bytes = SAMPLE_CSV.read_bytes()
    expected_hash = hashlib.sha256(csv_bytes).hexdigest()

    payload = _import_dataset(client, csv_bytes)
    assert payload["dataset_id"] == expected_hash
    manifest = payload["manifest"]
    assert manifest["content_hash"] == expected_hash
    assert manifest["row_count"] > 0
    assert manifest["columns"] == ["timestamp", "open", "high", "low", "close", "volume"]
    assert isinstance(manifest["inferred_time_range"], dict)

    dataset_path = runs_root / "users" / TEST_USER_ID / "imports" / expected_hash / "dataset.csv"
    assert dataset_path.exists()


def test_data_import_invalid_csv_returns_error_envelope(
    api_client: tuple[TestClient, Path],
) -> None:
    client, _ = api_client
    bad_csv = b"timestamp,open,high,low,close\n2026-01-01T00:00:00Z,1,2,0.5,1.5\n"
    response = client.post(
        "/api/v1/data/import",
        files={"file": ("bad.csv", bad_csv, "text/csv")},
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "DATA_INVALID"
    envelope = payload["error_envelope"]
    assert envelope["human_message"]
    assert envelope["recovery_hint"]


def test_create_run_from_dataset_visible_in_observability(
    api_client: tuple[TestClient, Path],
) -> None:
    client, _ = api_client
    imported = _import_dataset(client, SAMPLE_CSV.read_bytes())
    dataset_id = imported["dataset_id"]

    create_response = client.post(
        "/api/v1/runs",
        json={
            "dataset_id": dataset_id,
            "strategy_id": "hold",
            "params": {},
            "risk_level": 3,
        },
    )
    assert create_response.status_code in {200, 201}
    create_payload = create_response.json()
    run_id = create_payload["run_id"]
    assert create_payload["status"] == "COMPLETED"
    assert isinstance(create_payload.get("provenance"), dict)

    observability = client.get("/api/v1/observability/runs")
    assert observability.status_code == 200
    rows = observability.json().get("runs", [])
    assert any(row.get("run_id") == run_id for row in rows)


def test_status_endpoint_deterministic(api_client: tuple[TestClient, Path]) -> None:
    client, _ = api_client
    imported = _import_dataset(client, SAMPLE_CSV.read_bytes())
    create_response = client.post(
        "/api/v1/runs",
        json={
            "dataset_id": imported["dataset_id"],
            "strategy_id": "ma_cross",
            "params": {"fast_period": 2, "slow_period": 3},
            "risk_level": 2,
        },
    )
    assert create_response.status_code in {200, 201}
    run_id = create_response.json()["run_id"]

    first = client.get(f"/api/v1/runs/{run_id}/status")
    second = client.get(f"/api/v1/runs/{run_id}/status")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    payload = first.json()
    assert payload["state"] == "COMPLETED"
    assert payload["percent"] == 100
    assert isinstance(payload.get("last_event"), dict)


def test_summary_includes_available_ohlcv_timeframes(
    api_client: tuple[TestClient, Path],
) -> None:
    client, _ = api_client
    imported = _import_dataset(client, SAMPLE_CSV.read_bytes())
    create_response = client.post(
        "/api/v1/runs",
        json={
            "dataset_id": imported["dataset_id"],
            "strategy_id": "hold",
            "params": {},
            "risk_level": 3,
        },
    )
    assert create_response.status_code in {200, 201}
    run_id = create_response.json()["run_id"]

    summary = client.get(f"/api/v1/runs/{run_id}/summary")
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["ohlcv_available_timeframes"] == ["1m"]


def test_product_flow_has_no_network_access(
    api_client: tuple[TestClient, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = api_client

    def _fail_urlopen(*args, **kwargs):  # pragma: no cover - defensive guard
        raise AssertionError(f"Network call attempted: args={args} kwargs={kwargs}")

    monkeypatch.setattr(urllib.request, "urlopen", _fail_urlopen, raising=True)

    imported = _import_dataset(client, SAMPLE_CSV.read_bytes())
    create_response = client.post(
        "/api/v1/runs",
        json={
            "dataset_id": imported["dataset_id"],
            "strategy_id": "hold",
            "params": {},
            "risk_level": 3,
        },
    )
    assert create_response.status_code in {200, 201}
    run_id = create_response.json()["run_id"]
    strategies = client.get("/api/v1/strategies")
    assert strategies.status_code == 200
    assert isinstance(strategies.json(), list)
    summary = client.get(f"/api/v1/runs/{run_id}/summary")
    assert summary.status_code == 200
    assert summary.json()["ohlcv_available_timeframes"] == ["1m"]
