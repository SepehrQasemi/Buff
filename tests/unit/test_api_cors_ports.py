from __future__ import annotations

from apps.api.main import DEV_UI_PORT_ENV, _cors_allow_origins


def test_cors_defaults_to_localhost_3000(monkeypatch) -> None:
    monkeypatch.delenv(DEV_UI_PORT_ENV, raising=False)

    origins = _cors_allow_origins()

    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins


def test_cors_includes_dev_ui_port(monkeypatch) -> None:
    monkeypatch.setenv(DEV_UI_PORT_ENV, "13000")

    origins = _cors_allow_origins()

    assert "http://localhost:13000" in origins
    assert "http://127.0.0.1:13000" in origins


def test_cors_ignores_invalid_dev_ui_port(monkeypatch) -> None:
    monkeypatch.setenv(DEV_UI_PORT_ENV, "not-a-port")

    origins = _cors_allow_origins()

    assert "http://localhost:not-a-port" not in origins
    assert "http://127.0.0.1:not-a-port" not in origins
