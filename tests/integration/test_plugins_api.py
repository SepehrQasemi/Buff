import json

from fastapi.testclient import TestClient

from apps.api.main import app


def _write_validation(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_plugins_active_and_failed(monkeypatch, tmp_path):
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    plugins_root = artifacts_root / "plugins"

    _write_validation(
        plugins_root / "indicator" / "rsi" / "validation.json",
        {
            "plugin_id": "rsi",
            "plugin_type": "indicator",
            "status": "PASS",
            "errors": [],
            "validated_at_utc": "2026-02-01T00:00:00Z",
            "fingerprint": "abc",
            "name": "RSI",
            "version": "1.0.0",
            "category": "momentum",
        },
    )

    _write_validation(
        plugins_root / "strategy" / "bad" / "validation.json",
        {
            "plugin_id": "bad",
            "plugin_type": "strategy",
            "status": "FAIL",
            "errors": [{"rule_id": "SCHEMA_MISSING_FIELD", "message": "missing id"}],
            "validated_at_utc": "2026-02-01T00:00:00Z",
            "fingerprint": "def",
        },
    )

    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    client = TestClient(app)

    active = client.get("/api/v1/plugins/active")
    assert active.status_code == 200
    active_payload = active.json()
    assert active_payload["indicators"][0]["id"] == "rsi"
    assert active_payload["strategies"] == []

    failed = client.get("/api/v1/plugins/failed")
    assert failed.status_code == 200
    failed_payload = failed.json()
    assert failed_payload["indicators"] == []
    assert failed_payload["strategies"][0]["id"] == "bad"
    assert failed_payload["strategies"][0]["errors"]


def test_plugins_missing_artifacts_returns_empty(monkeypatch, tmp_path):
    artifacts_root = tmp_path / "missing"
    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    client = TestClient(app)

    active = client.get("/api/v1/plugins/active")
    assert active.status_code == 200
    active_payload = active.json()
    assert active_payload == {"indicators": [], "strategies": []}

    failed = client.get("/api/v1/plugins/failed")
    assert failed.status_code == 200
    failed_payload = failed.json()
    assert failed_payload == {"indicators": [], "strategies": []}
