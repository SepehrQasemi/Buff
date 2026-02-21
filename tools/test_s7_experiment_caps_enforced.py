from __future__ import annotations

import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from apps.api.main import app
from apps.api.phase6.experiment_contract import MAX_EXPERIMENT_CANDIDATES

TEST_USER = "gate-user"


def _run_config() -> dict[str, object]:
    return {
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
    }


def test_s7_experiment_caps_enforced(monkeypatch, tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("BUFF_DEFAULT_USER", TEST_USER)

    payload = {
        "schema_version": "1.0.0",
        "name": "s7-gate-caps",
        "candidates": [
            {
                "candidate_id": f"cand_{idx + 1:03d}",
                "run_config": _run_config(),
            }
            for idx in range(MAX_EXPERIMENT_CANDIDATES + 1)
        ],
    }

    with TestClient(app) as client:
        response = client.post("/api/v1/experiments", json=payload)

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "EXPERIMENT_CANDIDATES_LIMIT_EXCEEDED"
    assert isinstance(body.get("details"), dict)
    assert isinstance(body["details"].get("requested_count"), int)
    assert isinstance(body["details"].get("max_allowed"), int)
    assert body["details"]["requested_count"] == MAX_EXPERIMENT_CANDIDATES + 1
    assert body["details"]["max_allowed"] == MAX_EXPERIMENT_CANDIDATES
    assert isinstance(body.get("error_envelope"), dict)
    assert body["error_envelope"]["error_code"] == "EXPERIMENT_CANDIDATES_LIMIT_EXCEEDED"
    assert "Traceback" not in json.dumps(body, sort_keys=True)
