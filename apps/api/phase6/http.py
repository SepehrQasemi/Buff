from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


def error_payload(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = details or {}
    payload = {"code": code, "message": message, "details": normalized}
    payload["error"] = {"code": code, "message": message, "details": normalized}
    return payload


def error_response(
    status_code: int, code: str, message: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=error_payload(code, message, details))
