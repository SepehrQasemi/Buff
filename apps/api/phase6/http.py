from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from apps.api.errors import build_error_payload


def error_payload(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return build_error_payload(code, message, details)


def error_response(
    status_code: int, code: str, message: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=error_payload(code, message, details))
