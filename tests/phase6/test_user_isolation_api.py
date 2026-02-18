from __future__ import annotations

import hashlib
import hmac

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.security.user_context import canonical_auth_string


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


def _sign(secret: str, *, user_id: str, method: str, path: str, timestamp: int) -> str:
    canonical = canonical_auth_string(user_id, method, path, timestamp)
    return hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def _headers(user_id: str) -> dict[str, str]:
    return {"X-Buff-User": user_id}


def test_multi_user_isolation(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.delenv("BUFF_USER_HMAC_SECRET", raising=False)
    monkeypatch.delenv("BUFF_DEFAULT_USER", raising=False)

    client = TestClient(app)
    create = client.post("/api/v1/runs", json=_payload(), headers=_headers("user-a"))
    assert create.status_code == 201
    run_id = create.json()["run_id"]

    list_a = client.get("/api/v1/runs", headers=_headers("user-a"))
    assert list_a.status_code == 200
    assert [item["run_id"] for item in list_a.json()] == [run_id]

    list_b = client.get("/api/v1/runs", headers=_headers("user-b"))
    assert list_b.status_code == 200
    assert list_b.json() == []

    metrics_b = client.get(f"/api/v1/runs/{run_id}/metrics", headers=_headers("user-b"))
    assert metrics_b.status_code == 404
    assert metrics_b.json()["code"] == "RUN_NOT_FOUND"

    diagnostics_b = client.get(f"/api/v1/runs/{run_id}/diagnostics", headers=_headers("user-b"))
    assert diagnostics_b.status_code == 404
    assert diagnostics_b.json()["code"] == "RUN_NOT_FOUND"

    artifact_b = client.get(
        f"/api/v1/runs/{run_id}/artifacts/manifest.json",
        headers=_headers("user-b"),
    )
    assert artifact_b.status_code == 404
    assert artifact_b.json()["code"] == "RUN_NOT_FOUND"


def test_missing_user_header_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.delenv("BUFF_DEFAULT_USER", raising=False)
    monkeypatch.delenv("BUFF_USER_HMAC_SECRET", raising=False)

    client = TestClient(app)
    response = client.get("/api/v1/runs")
    assert response.status_code == 400
    assert response.json()["code"] == "USER_MISSING"


def test_user_header_traversal_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.delenv("BUFF_DEFAULT_USER", raising=False)
    monkeypatch.delenv("BUFF_USER_HMAC_SECRET", raising=False)

    client = TestClient(app)
    response = client.get("/api/v1/runs", headers=_headers("../evil"))
    assert response.status_code == 400
    assert response.json()["code"] == "USER_INVALID"


def test_run_id_traversal_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.delenv("BUFF_DEFAULT_USER", raising=False)
    monkeypatch.delenv("BUFF_USER_HMAC_SECRET", raising=False)

    client = TestClient(app)
    response = client.get("/api/v1/runs/%2e%2e/metrics", headers=_headers("user-a"))
    assert response.status_code == 400
    assert response.json()["code"] == "RUN_ID_INVALID"


def test_hmac_auth_enforced(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.delenv("BUFF_DEFAULT_USER", raising=False)
    monkeypatch.setenv("BUFF_USER_HMAC_SECRET", "top-secret")

    client = TestClient(app)
    missing_auth = client.get("/api/v1/runs", headers=_headers("alice"))
    assert missing_auth.status_code == 401
    assert missing_auth.json()["code"] == "AUTH_MISSING"

    now_ts = 1700000000
    signature = _sign(
        "top-secret",
        user_id="alice",
        method="GET",
        path="/api/v1/runs",
        timestamp=now_ts,
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("apps.api.security.user_context.time.time", lambda: now_ts)
        allowed = client.get(
            "/api/v1/runs",
            headers={
                "X-Buff-User": "alice",
                "X-Buff-Auth": signature,
                "X-Buff-Timestamp": str(now_ts),
            },
        )
    assert allowed.status_code == 200


def test_hmac_header_tamper_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.delenv("BUFF_DEFAULT_USER", raising=False)
    monkeypatch.setenv("BUFF_USER_HMAC_SECRET", "top-secret")

    now_ts = 1700000000
    signature_for_a = _sign(
        "top-secret",
        user_id="user-a",
        method="GET",
        path="/api/v1/runs",
        timestamp=now_ts,
    )
    client = TestClient(app)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("apps.api.security.user_context.time.time", lambda: now_ts)
        response = client.get(
            "/api/v1/runs",
            headers={
                "X-Buff-User": "user-b",
                "X-Buff-Auth": signature_for_a,
                "X-Buff-Timestamp": str(now_ts),
            },
        )
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_INVALID"


def test_hmac_timestamp_replay_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.delenv("BUFF_DEFAULT_USER", raising=False)
    monkeypatch.setenv("BUFF_USER_HMAC_SECRET", "top-secret")

    old_ts = 1700000000
    now_ts = old_ts + 301
    signature = _sign(
        "top-secret",
        user_id="alice",
        method="GET",
        path="/api/v1/runs",
        timestamp=old_ts,
    )
    client = TestClient(app)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("apps.api.security.user_context.time.time", lambda: now_ts)
        response = client.get(
            "/api/v1/runs",
            headers={
                "X-Buff-User": "alice",
                "X-Buff-Auth": signature,
                "X-Buff-Timestamp": str(old_ts),
            },
        )
    assert response.status_code == 401
    assert response.json()["code"] == "TIMESTAMP_INVALID"
