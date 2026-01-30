from __future__ import annotations


def sanitize_run_id(run_id: str) -> str:
    if not run_id:
        raise ValueError("missing_run_id")
    for ch in run_id:
        if not (ch.isalnum() or ch in {"_", "-"}):
            raise ValueError("invalid_run_id")
    return run_id
