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
        "name": "s7-gate-contract",
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


def _run_dir(runs_root: Path, run_id: str) -> Path:
    return runs_root / "users" / TEST_USER / "runs" / run_id


def test_s7_experiment_artifact_contract(monkeypatch, tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("BUFF_DEFAULT_USER", TEST_USER)

    with TestClient(app) as client:
        response = client.post("/api/v1/experiments", json=_experiment_payload())
        assert response.status_code == 201
        created = response.json()
        assert created["status"] == "COMPLETED"
        experiment_id = str(created["experiment_id"])

        experiment_root = runs_root / "users" / TEST_USER / "experiments" / experiment_id
        manifest_path = experiment_root / "experiment_manifest.json"
        comparison_path = experiment_root / "comparison_summary.json"
        assert manifest_path.exists(), "experiment_manifest.json missing"
        assert comparison_path.exists(), "comparison_summary.json missing"

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        assert isinstance(manifest, dict)
        assert isinstance(comparison, dict)

        completed_candidates = [
            item
            for item in manifest.get("candidates", [])
            if isinstance(item, dict) and item.get("status") == "COMPLETED"
        ]
        assert len(completed_candidates) >= 2
        run_ids = [str(item["run_id"]) for item in completed_candidates if item.get("run_id")]
        assert len(run_ids) >= 2

        expected_columns = {
            "candidate_index",
            "candidate_id",
            "run_id",
            "status",
            "strategy_id",
            "symbol",
            "timeframe",
            "risk_level",
            "total_return",
            "final_equity",
            "max_drawdown",
            "win_rate",
            "num_trades",
        }
        assert set(comparison.get("columns", [])) == expected_columns

        rows = comparison.get("rows", [])
        assert isinstance(rows, list)
        assert len(rows) >= 2
        by_run_id = {str(row.get("run_id")): row for row in rows if isinstance(row, dict)}
        for run_id in run_ids:
            assert run_id in by_run_id
            metrics = json.loads(
                (_run_dir(runs_root, run_id) / "metrics.json").read_text(encoding="utf-8")
            )
            row = by_run_id[run_id]
            # Ensure summary values are artifact-driven (copied from metrics.json), not recomputed elsewhere.
            assert row["strategy_id"] == metrics.get("strategy_id")
            assert row["symbol"] == metrics.get("symbol")
            assert row["timeframe"] == metrics.get("timeframe")
            assert row["risk_level"] == metrics.get("risk_level")
            assert row["total_return"] == metrics.get("total_return")
            assert row["final_equity"] == metrics.get("final_equity")
            assert row["max_drawdown"] == metrics.get("max_drawdown")
            assert row["win_rate"] == metrics.get("win_rate")
            assert row["num_trades"] == metrics.get("num_trades")
