from __future__ import annotations

import hashlib
import hmac

import pytest

from apps.api.security.user_context import (
    AUTH_HEADER,
    HMAC_SECRET_ENV,
    TIMESTAMP_HEADER,
    USER_HEADER,
    UserContextError,
    canonical_auth_string,
    resolve_user_context,
)


def _sign(secret: str, *, user_id: str, method: str, path: str, timestamp: int) -> str:
    canonical = canonical_auth_string(user_id, method, path, timestamp)
    return hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def test_user_missing_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BUFF_DEFAULT_USER", raising=False)
    monkeypatch.delenv(HMAC_SECRET_ENV, raising=False)
    with pytest.raises(UserContextError) as exc:
        resolve_user_context({}, "GET", "/api/v1/runs")
    assert exc.value.code == "USER_MISSING"


def test_user_invalid_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BUFF_DEFAULT_USER", raising=False)
    monkeypatch.delenv(HMAC_SECRET_ENV, raising=False)
    with pytest.raises(UserContextError) as exc:
        resolve_user_context({USER_HEADER: "../bad"}, "GET", "/api/v1/runs")
    assert exc.value.code == "USER_INVALID"


def test_secret_requires_auth_and_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(HMAC_SECRET_ENV, "secret")
    with pytest.raises(UserContextError) as missing_auth:
        resolve_user_context({USER_HEADER: "alice"}, "GET", "/api/v1/runs")
    assert missing_auth.value.code == "AUTH_MISSING"

    with pytest.raises(UserContextError) as missing_ts:
        resolve_user_context(
            {USER_HEADER: "alice", AUTH_HEADER: "deadbeef"},
            "GET",
            "/api/v1/runs",
        )
    assert missing_ts.value.code == "TIMESTAMP_MISSING"


def test_bad_timestamp_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(HMAC_SECRET_ENV, "secret")
    with pytest.raises(UserContextError) as exc:
        resolve_user_context(
            {
                USER_HEADER: "alice",
                AUTH_HEADER: "0" * 64,
                TIMESTAMP_HEADER: "not-a-number",
            },
            "GET",
            "/api/v1/runs",
        )
    assert exc.value.code == "TIMESTAMP_INVALID"


def test_bad_signature_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(HMAC_SECRET_ENV, "secret")
    with pytest.raises(UserContextError) as exc:
        resolve_user_context(
            {
                USER_HEADER: "alice",
                AUTH_HEADER: "0" * 64,
                TIMESTAMP_HEADER: "1700000000",
            },
            "GET",
            "/api/v1/runs",
            now_unix=1700000000,
        )
    assert exc.value.code == "AUTH_INVALID"


def test_valid_signature_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(HMAC_SECRET_ENV, "secret")
    timestamp = 1700000000
    signature = _sign(
        "secret",
        user_id="alice",
        method="GET",
        path="/api/v1/runs",
        timestamp=timestamp,
    )
    context = resolve_user_context(
        {
            USER_HEADER: "alice",
            AUTH_HEADER: signature,
            TIMESTAMP_HEADER: str(timestamp),
        },
        "GET",
        "/api/v1/runs",
        now_unix=timestamp,
    )
    assert context.user_id == "alice"
    assert context.auth_mode == "hmac_sha256"


def test_signature_path_normalization_ignores_query_and_trailing_slash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(HMAC_SECRET_ENV, "secret")
    timestamp = 1700000000
    signature = _sign(
        "secret",
        user_id="alice",
        method="GET",
        path="/api/v1/runs",
        timestamp=timestamp,
    )
    headers = {
        USER_HEADER: "alice",
        AUTH_HEADER: signature,
        TIMESTAMP_HEADER: str(timestamp),
    }

    for variant in ["/api/v1/runs", "/api/v1/runs/", "/api/v1/runs?limit=5"]:
        context = resolve_user_context(headers, "GET", variant, now_unix=timestamp)
        assert context.user_id == "alice"
