from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import app


def _write_legacy_run(base_runs_root: Path, run_id: str) -> Path:
    run_dir = base_runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "run_id": run_id,
                "created_at": "2026-01-01T00:00:00Z",
                "status": "COMPLETED",
                "inputs_hash": "legacy-hash",
                "data": {"symbol": "BTCUSDT", "timeframe": "1m"},
                "strategy": {"id": "hold"},
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "config.json").write_text("{}", encoding="utf-8")
    (run_dir / "metrics.json").write_text("{}", encoding="utf-8")
    (run_dir / "equity_curve.json").write_text("[]", encoding="utf-8")
    (run_dir / "decision_records.jsonl").write_text("{}\n", encoding="utf-8")
    (run_dir / "trades.jsonl").write_text("{}\n", encoding="utf-8")
    (run_dir / "ohlcv_1m.jsonl").write_text("{}\n", encoding="utf-8")
    (run_dir / "timeline.json").write_text("[]", encoding="utf-8")
    return run_dir


def test_ready_degrades_when_legacy_exists_without_default_user(monkeypatch, tmp_path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    _write_legacy_run(runs_root, "run-legacy")
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.delenv("BUFF_DEFAULT_USER", raising=False)

    client = TestClient(app)
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["checks"]["legacy_migration"]["code"] == "LEGACY_MIGRATION_REQUIRED"


def test_admin_migrates_legacy_runs_with_default_user(monkeypatch, tmp_path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    _write_legacy_run(runs_root, "run-legacy")
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("BUFF_DEFAULT_USER", "test-user")

    client = TestClient(app)
    ready = client.get("/api/v1/ready")
    assert ready.status_code == 200
    payload = ready.json()
    assert payload["status"] == "degraded"
    assert payload["checks"]["legacy_migration"]["code"] == "LEGACY_MIGRATION_REQUIRED"
    assert payload["checks"]["legacy_migration"]["legacy_runs"] == 1
    assert (runs_root / "run-legacy").exists()

    migrate = client.post("/api/v1/admin/migrate")
    assert migrate.status_code == 200
    migrate_payload = migrate.json()
    assert migrate_payload["status"] == "ok"
    assert migrate_payload["migrated_runs"] == 1
    assert migrate_payload["migrated_run_ids"] == ["run-legacy"]

    ready_after = client.get("/api/v1/ready")
    assert ready_after.status_code == 200
    assert ready_after.json()["status"] == "ready"

    migrated_manifest = (
        runs_root / "users" / "test-user" / "runs" / "run-legacy" / "manifest.json"
    ).read_text(encoding="utf-8")
    migrated_payload = json.loads(migrated_manifest)
    assert migrated_payload["meta"]["migrated_from_legacy"] is True
    assert migrated_payload["meta"]["owner_user_id"] == "test-user"

    runs = client.get("/api/v1/runs", headers={"X-Buff-User": "test-user"})
    assert runs.status_code == 200
    assert any(item.get("run_id") == "run-legacy" for item in runs.json())
