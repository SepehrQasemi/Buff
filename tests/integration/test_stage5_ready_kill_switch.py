from fastapi.testclient import TestClient

from apps.api.main import KILL_SWITCH_ENV, app


def _valid_run_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "data_source": {
            "type": "csv",
            "path": "tests/fixtures/phase6/sample.csv",
            "symbol": "BTCUSDT",
            "timeframe": "1m",
        },
        "strategy": {"id": "hold"},
        "risk": {"level": 3},
        "costs": {"commission_bps": 0, "slippage_bps": 0},
    }


def test_ready_endpoint_reports_ready(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.delenv(KILL_SWITCH_ENV, raising=False)

    client = TestClient(app)
    response = client.get("/api/v1/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["api_version"] == "1"
    assert payload["checks"]["runs_root"]["status"] == "ok"
    assert payload["checks"]["runs_root"]["path"] == str(runs_root)
    assert payload["checks"]["runs_root"]["writable"] is True
    assert payload["checks"]["registry"]["status"] == "ok"


def test_kill_switch_blocks_run_creation(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.setenv(KILL_SWITCH_ENV, "1")

    client = TestClient(app)
    response = client.post("/api/v1/runs", json=_valid_run_payload())

    assert response.status_code == 503
    payload = response.json()
    assert payload["error"]["code"] == "KILL_SWITCH_ENABLED"


def test_ready_endpoint_requires_runs_root(monkeypatch):
    monkeypatch.delenv("RUNS_ROOT", raising=False)
    client = TestClient(app)

    response = client.get("/api/v1/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["error"]["code"] == "RUNS_ROOT_UNSET"


def test_ready_endpoint_missing_runs_root(monkeypatch, tmp_path):
    runs_root = tmp_path / "missing"
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    client = TestClient(app)

    response = client.get("/api/v1/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["error"]["code"] == "RUNS_ROOT_MISSING"


def test_ready_endpoint_not_writable(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.setattr(
        "apps.api.main._check_runs_root_writable_read_only",
        lambda _path: (False, "blocked"),
    )
    client = TestClient(app)

    response = client.get("/api/v1/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["error"]["code"] == "RUNS_ROOT_NOT_WRITABLE"


def test_post_runs_requires_runs_root(monkeypatch):
    monkeypatch.delenv("RUNS_ROOT", raising=False)
    client = TestClient(app)

    response = client.post("/api/v1/runs", json=_valid_run_payload())

    assert response.status_code == 503
    payload = response.json()
    assert payload["code"] == "RUNS_ROOT_UNSET"
    assert payload["error"]["code"] == "RUNS_ROOT_UNSET"
    assert isinstance(payload.get("message"), str) and payload["message"].strip()
    assert isinstance(payload.get("details"), dict)


def test_post_runs_missing_runs_root(monkeypatch, tmp_path):
    runs_root = tmp_path / "missing"
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    client = TestClient(app)

    response = client.post("/api/v1/runs", json=_valid_run_payload())

    assert response.status_code == 503
    payload = response.json()
    assert payload["code"] == "RUNS_ROOT_MISSING"
    assert payload["error"]["code"] == "RUNS_ROOT_MISSING"
    assert isinstance(payload.get("details"), dict)


def test_post_runs_invalid_runs_root(monkeypatch, tmp_path):
    runs_root_file = tmp_path / "runs_root_file.txt"
    runs_root_file.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("RUNS_ROOT", str(runs_root_file))
    client = TestClient(app)

    response = client.post("/api/v1/runs", json=_valid_run_payload())

    assert response.status_code == 503
    payload = response.json()
    assert payload["code"] == "RUNS_ROOT_INVALID"
    assert payload["error"]["code"] == "RUNS_ROOT_INVALID"
    assert isinstance(payload.get("details"), dict)


def test_post_runs_not_writable(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.setattr(
        "apps.api.phase6.run_builder._check_runs_root_writable",
        lambda _path: (False, "blocked"),
    )
    client = TestClient(app)

    response = client.post("/api/v1/runs", json=_valid_run_payload())

    assert response.status_code == 503
    payload = response.json()
    assert payload["code"] == "RUNS_ROOT_NOT_WRITABLE"
    assert payload["error"]["code"] == "RUNS_ROOT_NOT_WRITABLE"
    assert isinstance(payload.get("details"), dict)
