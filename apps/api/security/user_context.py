from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
from dataclasses import dataclass
from typing import Mapping

USER_HEADER = "X-Buff-User"
AUTH_HEADER = "X-Buff-Auth"
TIMESTAMP_HEADER = "X-Buff-Timestamp"

DEFAULT_USER_ENV = "BUFF_DEFAULT_USER"
HMAC_SECRET_ENV = "BUFF_USER_HMAC_SECRET"
MAX_TIMESTAMP_SKEW_SECONDS = 300

USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


@dataclass(frozen=True)
class UserContext:
    user_id: str
    auth_mode: str
    used_default_user: bool = False


@dataclass(frozen=True)
class UserContextError(Exception):
    status_code: int
    code: str
    message: str
    details: dict[str, object]


def is_valid_user_id(candidate: str) -> bool:
    value = (candidate or "").strip()
    if value in {"", ".", ".."}:
        return False
    return bool(USER_ID_PATTERN.match(value))


def canonical_auth_string(user_id: str, method: str, path: str, timestamp: int) -> str:
    return f"{user_id}\n{method.upper()}\n{path}\n{timestamp}"


def _error(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> UserContextError:
    return UserContextError(
        status_code=status_code,
        code=code,
        message=message,
        details=details or {},
    )


def resolve_user_context(
    headers: Mapping[str, str],
    method: str,
    path: str,
    *,
    now_unix: int | None = None,
) -> UserContext:
    raw_user = (headers.get(USER_HEADER) or "").strip()
    used_default = False
    if not raw_user:
        default_user = (os.getenv(DEFAULT_USER_ENV) or "").strip()
        if not default_user:
            raise _error(400, "USER_MISSING", "X-Buff-User header is required")
        raw_user = default_user
        used_default = True

    if not is_valid_user_id(raw_user):
        raise _error(
            400,
            "USER_INVALID",
            "Invalid user id",
            {"user_id": raw_user},
        )

    secret = os.getenv(HMAC_SECRET_ENV)
    if not secret:
        mode = "default_user" if used_default else "header_only"
        return UserContext(user_id=raw_user, auth_mode=mode, used_default_user=used_default)

    auth_header = (headers.get(AUTH_HEADER) or "").strip()
    if not auth_header:
        raise _error(401, "AUTH_MISSING", "X-Buff-Auth header is required")

    ts_header = (headers.get(TIMESTAMP_HEADER) or "").strip()
    if not ts_header:
        raise _error(401, "TIMESTAMP_MISSING", "X-Buff-Timestamp header is required")
    try:
        timestamp = int(ts_header)
    except ValueError as exc:
        raise _error(
            401,
            "TIMESTAMP_INVALID",
            "X-Buff-Timestamp must be unix seconds",
            {"timestamp": ts_header},
        ) from exc

    now_ts = int(time.time()) if now_unix is None else int(now_unix)
    if abs(now_ts - timestamp) > MAX_TIMESTAMP_SKEW_SECONDS:
        raise _error(
            401,
            "TIMESTAMP_INVALID",
            "X-Buff-Timestamp outside allowed skew",
            {"timestamp": timestamp, "now": now_ts, "max_skew_seconds": MAX_TIMESTAMP_SKEW_SECONDS},
        )

    canonical = canonical_auth_string(raw_user, method, path, timestamp)
    expected = hmac.new(
        secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    provided = auth_header.lower()
    if not hmac.compare_digest(expected, provided):
        raise _error(401, "AUTH_INVALID", "X-Buff-Auth signature invalid")

    return UserContext(user_id=raw_user, auth_mode="hmac_sha256", used_default_user=used_default)
