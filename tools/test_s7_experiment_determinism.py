from __future__ import annotations

import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from apps.api.main import app

TEST_USER = "gate-user"


def _experiment_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "name": "s7-gate-determinism",
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


def test_s7_experiment_determinism(monkeypatch, tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("BUFF_DEFAULT_USER", TEST_USER)

    with TestClient(app) as client:
        payload = _experiment_payload()

        first = client.post("/api/v1/experiments", json=payload)
        assert first.status_code == 201
        first_json = first.json()
        experiment_id = str(first_json["experiment_id"])
        experiment_digest = str(first_json["experiment_digest"])
        assert experiment_id == f"exp_{experiment_digest[:12]}"

        experiment_root = runs_root / "users" / TEST_USER / "experiments" / experiment_id
        manifest_path = experiment_root / "experiment_manifest.json"
        comparison_path = experiment_root / "comparison_summary.json"
        assert manifest_path.exists()
        assert comparison_path.exists()

        first_manifest_bytes = manifest_path.read_bytes()
        first_comparison_bytes = comparison_path.read_bytes()

        second = client.post("/api/v1/experiments", json=_experiment_payload())
        assert second.status_code == 200
        second_json = second.json()

        assert second_json["experiment_id"] == experiment_id
        assert second_json["experiment_digest"] == experiment_digest
        assert second_json["experiment_id"] == f"exp_{second_json['experiment_digest'][:12]}"

        second_manifest_bytes = manifest_path.read_bytes()
        second_comparison_bytes = comparison_path.read_bytes()
        assert second_manifest_bytes == first_manifest_bytes
        assert second_comparison_bytes == first_comparison_bytes

        first_manifest = json.loads(first_manifest_bytes.decode("utf-8"))
        second_manifest = json.loads(second_manifest_bytes.decode("utf-8"))
        assert first_manifest.get("status") == second_manifest.get("status")
        assert first_manifest.get("summary") == second_manifest.get("summary")
        assert first_manifest.get("candidates") == second_manifest.get("candidates")

        first_comparison = json.loads(first_comparison_bytes.decode("utf-8"))
        second_comparison = json.loads(second_comparison_bytes.decode("utf-8"))
        assert first_comparison.get("counts") == second_comparison.get("counts")
        assert first_comparison.get("columns") == second_comparison.get("columns")
        assert first_comparison.get("rows") == second_comparison.get("rows")
