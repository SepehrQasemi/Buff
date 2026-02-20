from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app

TEST_USER_ID = "test-user"
SAMPLE_PATH = Path("tests/fixtures/phase6/sample.csv").as_posix()
CROSS_PATH = Path("tests/fixtures/phase6/cross.csv").as_posix()


@pytest.fixture
def experiment_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    runs_root = tmp_path / "runs_root"
    runs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("BUFF_DEFAULT_USER", TEST_USER_ID)
    return runs_root


def _user_root(runs_root: Path) -> Path:
    return runs_root / "users" / TEST_USER_ID


def _experiments_root(runs_root: Path) -> Path:
    return _user_root(runs_root) / "experiments"


def _run_payload(*, path: str, strategy: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "data_source": {
            "type": "csv",
            "path": path,
            "symbol": "BTCUSDT",
            "timeframe": "1m",
        },
        "strategy": strategy,
        "risk": {"level": 3},
        "costs": {"commission_bps": 0.0, "slippage_bps": 0.0},
    }


def _experiment_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "name": "s7-experiment",
        "candidates": [
            {
                "candidate_id": "hold_a",
                "run_config": _run_payload(path=SAMPLE_PATH, strategy={"id": "hold", "params": {}}),
            },
            {
                "candidate_id": "cross_b",
                "run_config": _run_payload(
                    path=CROSS_PATH,
                    strategy={"id": "ma_cross", "params": {"fast_period": 2, "slow_period": 3}},
                ),
            },
        ],
    }


def test_experiment_fingerprint_is_deterministic(experiment_env: Path) -> None:
    client = TestClient(app)
    payload = _experiment_payload()
    first = client.post("/api/v1/experiments", json=payload)
    second = client.post("/api/v1/experiments", json=payload)
    try:
        assert first.status_code == 201
        assert second.status_code == 200
        first_json = first.json()
        second_json = second.json()
        assert first_json["experiment_id"] == second_json["experiment_id"]
        assert first_json["experiment_digest"] == second_json["experiment_digest"]

        experiment_dir = _experiments_root(experiment_env) / first_json["experiment_id"]
        manifest = json.loads(
            (experiment_dir / "experiment_manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["experiment_digest"] == first_json["experiment_digest"]
    finally:
        client.close()


def test_experiment_writes_manifest_and_comparison_summary(experiment_env: Path) -> None:
    client = TestClient(app)
    response = client.post("/api/v1/experiments", json=_experiment_payload())
    try:
        assert response.status_code == 201
        payload = response.json()
        assert payload["status"] == "COMPLETED"

        experiment_dir = _experiments_root(experiment_env) / payload["experiment_id"]
        manifest_path = experiment_dir / "experiment_manifest.json"
        comparison_path = experiment_dir / "comparison_summary.json"
        assert manifest_path.exists()
        assert comparison_path.exists()

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))

        assert manifest["status"] == "COMPLETED"
        assert len(manifest["candidates"]) == 2
        run_ids = [item.get("run_id") for item in manifest["candidates"]]
        assert all(isinstance(run_id, str) and run_id for run_id in run_ids)
        assert comparison["status"] == "COMPLETED"
        assert comparison["counts"] == {"total_candidates": 2, "succeeded": 2, "failed": 0}
        assert len(comparison["rows"]) == 2
        assert {row["run_id"] for row in comparison["rows"]} == set(run_ids)

        manifest_api = client.get(f"/api/v1/experiments/{payload['experiment_id']}/manifest")
        comparison_api = client.get(f"/api/v1/experiments/{payload['experiment_id']}/comparison")
        assert manifest_api.status_code == 200
        assert comparison_api.status_code == 200
        assert manifest_api.json() == manifest
        assert comparison_api.json() == comparison
    finally:
        client.close()


def test_experiment_partial_failure_preserves_artifacts(experiment_env: Path) -> None:
    client = TestClient(app)
    payload = _experiment_payload()
    payload["candidates"].append(
        {
            "candidate_id": "bad_cfg",
            "run_config": _run_payload(
                path=SAMPLE_PATH,
                strategy={"id": "unknown_strategy", "params": {}},
            ),
        }
    )
    response = client.post("/api/v1/experiments", json=payload)
    try:
        assert response.status_code == 201
        response_payload = response.json()
        assert response_payload["status"] == "PARTIAL"

        experiment_dir = _experiments_root(experiment_env) / response_payload["experiment_id"]
        manifest = json.loads(
            (experiment_dir / "experiment_manifest.json").read_text(encoding="utf-8")
        )
        comparison = json.loads(
            (experiment_dir / "comparison_summary.json").read_text(encoding="utf-8")
        )

        assert manifest["status"] == "PARTIAL"
        assert manifest["summary"] == {"total_candidates": 3, "succeeded": 2, "failed": 1}

        failed = [item for item in manifest["candidates"] if item.get("status") == "FAILED"]
        assert len(failed) == 1
        assert failed[0]["candidate_id"] == "bad_cfg"
        assert failed[0]["run_id"] is None
        assert failed[0]["error"]["code"] in {"STRATEGY_INVALID", "RUN_CONFIG_INVALID"}

        assert comparison["status"] == "PARTIAL"
        assert comparison["counts"] == {"total_candidates": 3, "succeeded": 2, "failed": 1}
        assert len(comparison["rows"]) == 2
        assert all(row["candidate_id"] != "bad_cfg" for row in comparison["rows"])
    finally:
        client.close()
