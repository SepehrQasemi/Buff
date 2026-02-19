from __future__ import annotations

import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from apps.api.main import app


def _payload() -> dict[str, object]:
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
        "costs": {"commission_bps": 0, "slippage_bps": 0},
    }


def test_sim_only_manifest_invariant(monkeypatch, tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("BUFF_DEFAULT_USER", "gate-user")

    client = TestClient(app)
    response = client.post("/api/v1/runs", json=_payload())
    assert response.status_code in {200, 201}
    run_id = response.json()["run_id"]

    run_dir = runs_root / "users" / "gate-user" / "runs" / run_id
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["execution_mode"] == "SIM_ONLY"
    assert manifest["capabilities"] == ["SIMULATION", "DATA_READONLY"]

    detail = client.get(f"/api/v1/observability/runs/{run_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["provenance"]["stage_token"] == "S5_EXECUTION_SAFETY_BOUNDARIES"
