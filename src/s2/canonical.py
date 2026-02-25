from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable


def canonical_json_text(obj: object) -> str:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_json_bytes(obj: object) -> bytes:
    return canonical_json_text(obj).encode("utf-8")


def sha256_hex_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_hex_file(path: Path) -> str:
    return sha256_hex_bytes(path.read_bytes())


def write_canonical_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(payload))


def write_canonical_jsonl(path: Path, rows: Iterable[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = [canonical_json_bytes(row) for row in rows]
    if not encoded:
        path.write_bytes(b"")
        return
    path.write_bytes(b"\n".join(encoded) + b"\n")
