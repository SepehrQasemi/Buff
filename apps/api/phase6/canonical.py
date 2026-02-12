from __future__ import annotations

from pathlib import Path
from typing import Iterable

from audit.canonical_json import canonical_json, canonical_json_bytes

from .numeric import normalize_numbers


def to_canonical_json(obj: object) -> str:
    return canonical_json(normalize_numbers(obj))


def to_canonical_bytes(obj: object) -> bytes:
    return canonical_json_bytes(normalize_numbers(obj))


def write_canonical_json(path: Path, payload: object) -> None:
    normalized = normalize_numbers(payload)
    data = canonical_json(normalized).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        try:
            import os

            os.fsync(handle.fileno())
        except OSError:
            pass


def write_canonical_jsonl(path: Path, rows: Iterable[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        for row in rows:
            normalized = normalize_numbers(row)
            line = canonical_json(normalized).encode("utf-8") + b"\n"
            handle.write(line)
        handle.flush()
        try:
            import os

            os.fsync(handle.fileno())
        except OSError:
            pass
