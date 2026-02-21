from __future__ import annotations

import json
import re
from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from apps.api.main import app

TEST_USER = "gate-user"
_CANONICAL_CODE = re.compile(r"^[A-Z0-9_]+$")


def _valid_run_config() -> dict[str, object]:
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


def _invalid_run_config() -> dict[str, object]:
    payload = _valid_run_config()
    payload["strategy"] = {"id": "unknown_strategy", "params": {}}
    return payload


def test_s7_experiment_fail_closed_partial(monkeypatch, tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("BUFF_DEFAULT_USER", TEST_USER)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/experiments",
            json={
                "schema_version": "1.0.0",
                "name": "s7-gate-fail-closed",
                "candidates": [
                    {"candidate_id": "ok_one", "run_config": _valid_run_config()},
                    {"candidate_id": "bad_one", "run_config": _invalid_run_config()},
                ],
            },
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["status"] == "PARTIAL"
        assert payload["counts"] == {"total_candidates": 2, "succeeded": 1, "failed": 1}

        experiment_id = str(payload["experiment_id"])
        manifest_resp = client.get(f"/api/v1/experiments/{experiment_id}/manifest")
        assert manifest_resp.status_code == 200
        manifest = manifest_resp.json()
        assert manifest["status"] == "PARTIAL"
        assert manifest["summary"] == {"total_candidates": 2, "succeeded": 1, "failed": 1}

        candidates = [item for item in manifest.get("candidates", []) if isinstance(item, dict)]
        assert len(candidates) == 2
        by_id = {str(item.get("candidate_id")): item for item in candidates}
        assert by_id["ok_one"]["status"] == "COMPLETED"
        assert by_id["ok_one"]["run_id"]
        assert by_id["bad_one"]["status"] == "FAILED"
        assert by_id["bad_one"]["run_id"] is None

        error_payload = by_id["bad_one"].get("error")
        assert isinstance(error_payload, dict)
        code = str(error_payload.get("code") or "")
        message = str(error_payload.get("message") or "")
        assert _CANONICAL_CODE.fullmatch(code)
        assert code in {"STRATEGY_INVALID", "RUN_CONFIG_INVALID", "RISK_INVALID", "DATA_INVALID"}
        assert "Traceback" not in message
        assert "Traceback" not in json.dumps(error_payload, sort_keys=True)

        comparison_resp = client.get(f"/api/v1/experiments/{experiment_id}/comparison")
        assert comparison_resp.status_code == 200
        comparison = comparison_resp.json()
        assert comparison["status"] == "PARTIAL"
        assert comparison["counts"] == {"total_candidates": 2, "succeeded": 1, "failed": 1}
        rows = [item for item in comparison.get("rows", []) if isinstance(item, dict)]
        assert len(rows) == 1
        assert rows[0]["candidate_id"] == "ok_one"
