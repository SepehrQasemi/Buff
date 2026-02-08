from __future__ import annotations

from typing import Any

from fastapi import HTTPException


def build_error_payload(
    code: str, message: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "details": details or {},
    }


def raise_api_error(
    status_code: int, code: str, message: str, details: dict[str, Any] | None = None
) -> None:
    raise HTTPException(
        status_code=status_code,
        detail=build_error_payload(code, message, details),
    )
