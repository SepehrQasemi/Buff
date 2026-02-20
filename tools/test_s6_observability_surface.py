from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from apps.api.main import app

TEST_USER = "gate-user"


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


def _run_dir(runs_root: Path, run_id: str) -> Path:
    return runs_root / "users" / TEST_USER / "runs" / run_id


def _snapshot_tree(root: Path) -> dict[str, tuple[bool, int, int]]:
    entries = [root, *root.rglob("*")]
    snapshot: dict[str, tuple[bool, int, int]] = {}
    for entry in entries:
        if not entry.exists():
            continue
        relative = "." if entry == root else entry.relative_to(root).as_posix()
        stats = entry.stat()
        snapshot[relative] = (entry.is_dir(), stats.st_mtime_ns, stats.st_size)
    return snapshot


def test_observability_routes_are_read_only() -> None:
    routes = {
        route.path: set(route.methods or set())
        for route in app.routes
        if getattr(route, "path", "")
    }

    required_paths = {
        "/api/v1/health/ready",
        "/api/v1/observability/runs",
        "/api/v1/observability/runs/{run_id}",
        "/api/v1/observability/registry",
        "/api/v1/runs/{run_id}/metrics",
    }
    for path in required_paths:
        assert path in routes
        assert "GET" in routes[path]

    for path, methods in routes.items():
        if not path.startswith("/api/v1/observability"):
            continue
        assert methods <= {"GET", "HEAD", "OPTIONS"}


def test_observability_payloads_and_corruption_detection(monkeypatch, tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("BUFF_DEFAULT_USER", TEST_USER)
    monkeypatch.delenv("DEMO_MODE", raising=False)

    client = TestClient(app)

    create = client.post("/api/v1/runs", json=_payload())
    assert create.status_code in {200, 201}
    run_id = create.json()["run_id"]

    ready = client.get("/api/v1/health/ready")
    assert ready.status_code == 200
    ready_payload = ready.json()
    assert ready_payload["status"] == "ready"
    assert ready_payload["stage_token"] == "S5_EXECUTION_SAFETY_BOUNDARIES"
    assert isinstance(ready_payload.get("checks"), list)
    check_names = {item.get("name") for item in ready_payload["checks"]}
    assert {"runs_root", "registry_access", "run_integrity"}.issubset(check_names)

    runs_resp = client.get("/api/v1/observability/runs")
    assert runs_resp.status_code == 200
    runs_payload = runs_resp.json()
    assert runs_payload["stage_token"] == "S5_EXECUTION_SAFETY_BOUNDARIES"
    assert runs_payload["total"] >= 1
    run_entry = next(item for item in runs_payload["runs"] if item["run_id"] == run_id)
    assert {
        "run_id",
        "state",
        "strategy_id",
        "risk_level",
        "artifact_status",
        "validation_status",
    }.issubset(run_entry)

    detail_resp = client.get(f"/api/v1/observability/runs/{run_id}")
    assert detail_resp.status_code == 200
    detail_payload = detail_resp.json()
    assert detail_payload["provenance"]["stage_token"] == "S5_EXECUTION_SAFETY_BOUNDARIES"
    assert detail_payload["validation"]["status"] == "pass"
    assert isinstance(detail_payload["artifact_integrity"]["files"], list)

    metrics_path = _run_dir(runs_root, run_id) / "metrics.json"
    metrics_path.unlink()

    degraded_ready = client.get("/api/v1/health/ready")
    assert degraded_ready.status_code == 200
    degraded_payload = degraded_ready.json()
    assert degraded_payload["status"] == "not_ready"
    integrity_check = next(
        item for item in degraded_payload["checks"] if item["name"] == "run_integrity"
    )
    assert integrity_check["ok"] is False

    degraded_detail = client.get(f"/api/v1/observability/runs/{run_id}")
    assert degraded_detail.status_code == 200
    degraded_detail_payload = degraded_detail.json()
    assert degraded_detail_payload["validation"]["status"] == "fail"
    envelope = degraded_detail_payload["error_envelope"]
    assert envelope
    assert {
        "error_code",
        "human_message",
        "recovery_hint",
        "artifact_reference",
        "provenance",
    }.issubset(envelope)
    assert envelope["provenance"]["run_id"] == run_id

    registry_resp = client.get("/api/v1/observability/registry")
    assert registry_resp.status_code == 200
    registry_payload = registry_resp.json()
    assert "registry_integrity_status" in registry_payload
    assert "plugin_load_status" in registry_payload
    assert "failed_plugins" in registry_payload


def test_observability_gets_do_not_mutate_runs_root(monkeypatch, tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("BUFF_DEFAULT_USER", TEST_USER)
    monkeypatch.delenv("DEMO_MODE", raising=False)

    client = TestClient(app)
    create = client.post("/api/v1/runs", json=_payload())
    assert create.status_code in {200, 201}
    run_id = create.json()["run_id"]

    before = _snapshot_tree(runs_root)

    paths = (
        "/api/v1/health/ready",
        "/api/v1/observability/runs",
        f"/api/v1/observability/runs/{run_id}",
        "/api/v1/observability/registry",
        f"/api/v1/runs/{run_id}/metrics",
    )
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200

    after = _snapshot_tree(runs_root)
    assert after == before
