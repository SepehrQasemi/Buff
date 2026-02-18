from __future__ import annotations

import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from apps.api.main import app

_PATH_PARAM_VALUES = {
    "run_id": "dummy-run",
    "name": "manifest.json",
}


def _materialize_path(path: str) -> str:
    pattern = re.compile(r"{([^}:]+)(:[^}]*)?}")

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return _PATH_PARAM_VALUES.get(key, "dummy")

    return pattern.sub(_replace, path)


def _target_run_routes() -> list[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        path = route.path
        is_runs_path = path.startswith("/api/runs") or path.startswith("/api/v1/runs")
        is_artifact_path = "{run_id}" in path and "/artifacts" in path
        if not (is_runs_path or is_artifact_path):
            continue
        for method in sorted(route.methods):
            if method in {"HEAD", "OPTIONS"}:
                continue
            routes.add((method, path))
    return sorted(routes, key=lambda item: (item[1], item[0]))


@pytest.mark.parametrize(("method", "path"), _target_run_routes())
def test_run_routes_fail_closed_without_user_context(
    monkeypatch: pytest.MonkeyPatch, method: str, path: str
) -> None:
    monkeypatch.delenv("BUFF_DEFAULT_USER", raising=False)
    monkeypatch.delenv("BUFF_USER_HMAC_SECRET", raising=False)

    target_path = _materialize_path(path)
    kwargs: dict[str, object] = {}
    if method in {"POST", "PUT", "PATCH"}:
        kwargs["json"] = {}

    client = TestClient(app)
    response = client.request(method, target_path, **kwargs)
    details = f"{method} {target_path} leaked: status={response.status_code} body={response.text}"

    assert response.status_code in {400, 401}, details
    payload = response.json()
    assert payload.get("code") == "USER_MISSING", details
