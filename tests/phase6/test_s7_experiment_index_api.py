from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app

SAMPLE_PATH = Path("tests/fixtures/phase6/sample.csv").as_posix()


@pytest.fixture
def experiment_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    runs_root = tmp_path / "runs_root"
    runs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("BUFF_DEFAULT_USER", "index-default-user")
    return runs_root


def _user_root(runs_root: Path, user_id: str) -> Path:
    return runs_root / "users" / user_id


def _experiments_root(runs_root: Path, user_id: str) -> Path:
    return _user_root(runs_root, user_id) / "experiments"


def _run_payload(
    *, strategy_id: str = "hold", params: dict[str, object] | None = None
) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "data_source": {
            "type": "csv",
            "path": SAMPLE_PATH,
            "symbol": "BTCUSDT",
            "timeframe": "1m",
        },
        "strategy": {"id": strategy_id, "params": params or {}},
        "risk": {"level": 3},
        "costs": {"commission_bps": 0.0, "slippage_bps": 0.0},
    }


def _experiment_payload(*, candidate_id: str, strategy_id: str = "hold") -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "name": f"s7-index-{candidate_id}",
        "candidates": [
            {
                "candidate_id": candidate_id,
                "run_config": _run_payload(strategy_id=strategy_id),
            },
            {
                "candidate_id": f"{candidate_id}_alt",
                "run_config": _run_payload(strategy_id="hold"),
            },
        ],
    }


def _create_experiment(
    client: TestClient, user_id: str, payload: dict[str, object]
) -> dict[str, object]:
    response = client.post("/api/v1/experiments", json=payload, headers={"X-Buff-User": user_id})
    assert response.status_code in {200, 201}, response.text
    return response.json()


def _set_manifest_created_at(experiment_dir: Path, created_at: str) -> None:
    manifest_path = experiment_dir / "experiment_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["created_at"] = created_at
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_experiments_index_returns_entries_for_user(experiment_env: Path) -> None:
    client = TestClient(app)
    try:
        created = _create_experiment(
            client,
            "alice",
            _experiment_payload(candidate_id="alpha"),
        )
        response = client.get("/api/v1/experiments", headers={"X-Buff-User": "alice"})
        assert response.status_code == 200
        payload = response.json()
        assert isinstance(payload, list)
        assert len(payload) == 1

        item = payload[0]
        assert item["experiment_id"] == created["experiment_id"]
        assert item["status"] in {"COMPLETED", "PARTIAL", "FAILED"}
        assert isinstance(item["succeeded_count"], int)
        assert isinstance(item["failed_count"], int)
        assert isinstance(item["total_candidates"], int)
        assert item["total_candidates"] >= item["succeeded_count"] + item["failed_count"]
        assert item["created_at"] is None or isinstance(item["created_at"], str)
    finally:
        client.close()


def test_experiments_index_ordering_is_deterministic(experiment_env: Path) -> None:
    client = TestClient(app)
    try:
        first = _create_experiment(
            client,
            "alice",
            _experiment_payload(candidate_id="older", strategy_id="hold"),
        )
        second = _create_experiment(
            client,
            "alice",
            _experiment_payload(candidate_id="newer", strategy_id="hold"),
        )
        experiments_root = _experiments_root(experiment_env, "alice")
        _set_manifest_created_at(experiments_root / first["experiment_id"], "2026-01-01T00:00:00Z")
        _set_manifest_created_at(experiments_root / second["experiment_id"], "2026-01-02T00:00:00Z")

        first_index = client.get("/api/v1/experiments", headers={"X-Buff-User": "alice"})
        second_index = client.get("/api/v1/experiments", headers={"X-Buff-User": "alice"})
        assert first_index.status_code == 200
        assert second_index.status_code == 200

        first_payload = first_index.json()
        second_payload = second_index.json()
        assert [item["experiment_id"] for item in first_payload] == [
            second["experiment_id"],
            first["experiment_id"],
        ]
        assert first_payload == second_payload
    finally:
        client.close()


def test_experiments_index_marks_broken_manifest(experiment_env: Path) -> None:
    client = TestClient(app)
    try:
        created = _create_experiment(
            client,
            "alice",
            _experiment_payload(candidate_id="broken"),
        )
        manifest_path = (
            _experiments_root(experiment_env, "alice")
            / created["experiment_id"]
            / "experiment_manifest.json"
        )
        manifest_path.write_text("{broken json", encoding="utf-8")

        response = client.get("/api/v1/experiments", headers={"X-Buff-User": "alice"})
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        item = payload[0]
        assert item["experiment_id"] == created["experiment_id"]
        assert item["status"] == "BROKEN"
        assert item["succeeded_count"] == 0
        assert item["failed_count"] == 0
        assert item["total_candidates"] == 0
    finally:
        client.close()


def test_experiments_index_isolated_per_user(experiment_env: Path) -> None:
    client = TestClient(app)
    try:
        alice = _create_experiment(client, "alice", _experiment_payload(candidate_id="alice"))
        bob = _create_experiment(client, "bob", _experiment_payload(candidate_id="bob"))

        alice_index = client.get("/api/v1/experiments", headers={"X-Buff-User": "alice"})
        bob_index = client.get("/api/v1/experiments", headers={"X-Buff-User": "bob"})
        assert alice_index.status_code == 200
        assert bob_index.status_code == 200

        alice_ids = {item["experiment_id"] for item in alice_index.json()}
        bob_ids = {item["experiment_id"] for item in bob_index.json()}
        assert alice["experiment_id"] in alice_ids
        assert bob["experiment_id"] not in alice_ids
        assert bob["experiment_id"] in bob_ids
        assert alice["experiment_id"] not in bob_ids
    finally:
        client.close()
