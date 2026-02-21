from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from apps.api.main import app
from apps.api.phase6 import experiment_builder as s7_builder

TEST_USER = "gate-user"


def _experiment_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "name": "s7-gate-lock",
        "candidates": [
            {
                "candidate_id": "hold_a",
                "run_config": {
                    "schema_version": "1.0.0",
                    "data_source": {
                        "type": "csv",
                        "path": "tests/fixtures/phase6/sample.csv",
                        "symbol": "BTCUSDT",
                        "timeframe": "1m",
                    },
                    "strategy": {"id": "hold", "params": {}},
                    "risk": {"level": 3},
                    "costs": {"commission_bps": 0.0, "slippage_bps": 0.0},
                },
            },
            {
                "candidate_id": "cross_b",
                "run_config": {
                    "schema_version": "1.0.0",
                    "data_source": {
                        "type": "csv",
                        "path": "tests/fixtures/phase6/cross.csv",
                        "symbol": "BTCUSDT",
                        "timeframe": "1m",
                    },
                    "strategy": {"id": "ma_cross", "params": {"fast_period": 2, "slow_period": 3}},
                    "risk": {"level": 3},
                    "costs": {"commission_bps": 0.0, "slippage_bps": 0.0},
                },
            },
        ],
    }


def _submit(
    payload: dict[str, object], barrier: threading.Barrier
) -> tuple[int, dict[str, object]]:
    with TestClient(app) as client:
        barrier.wait(timeout=5.0)
        response = client.post("/api/v1/experiments", json=payload)
        return response.status_code, response.json()


def test_s7_experiment_lock_enforced(monkeypatch, tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("BUFF_DEFAULT_USER", TEST_USER)

    original_create_run = s7_builder.create_run

    def delayed_create_run(payload: dict[str, object], *, user_id: str | None = None):
        # Hold experiment lock long enough for competing request timeout.
        time.sleep(0.2)
        return original_create_run(payload, user_id=user_id)

    monkeypatch.setattr(s7_builder, "create_run", delayed_create_run)
    monkeypatch.setattr(s7_builder, "_EXPERIMENT_LOCK_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(s7_builder, "_EXPERIMENT_LOCK_POLL_SECONDS", 0.005)

    payload = _experiment_payload()
    barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_submit, payload, barrier) for _ in range(2)]
        results = [future.result(timeout=15.0) for future in futures]

    successes = [item for item in results if item[0] in {200, 201}]
    failures = [item for item in results if item[0] == 503]
    assert len(successes) == 1
    assert len(failures) == 1

    _, failure_payload = failures[0]
    assert failure_payload["code"] == "EXPERIMENT_LOCK_TIMEOUT"
    assert isinstance(failure_payload.get("details"), dict)
    assert "experiment_id" in failure_payload["details"]

    _, success_payload = successes[0]
    experiment_id = str(success_payload["experiment_id"])
    experiment_root = runs_root / "users" / TEST_USER / "experiments" / experiment_id
    manifest_path = experiment_root / "experiment_manifest.json"
    comparison_path = experiment_root / "comparison_summary.json"
    assert manifest_path.exists()
    assert comparison_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    assert manifest["experiment_id"] == experiment_id
    assert comparison["experiment_id"] == experiment_id
    assert isinstance(comparison.get("rows"), list)
