from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class IdempotencyInspectError(RuntimeError):
    pass


def open_idempotency_db(path: str) -> sqlite3.Connection:
    db_path = Path(path)
    if not db_path.exists():
        raise FileNotFoundError(f"idempotency_db_not_found:{db_path}")
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    try:
        return sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise IdempotencyInspectError("idempotency_db_open_error") from exc


def fetch_all_records(conn: sqlite3.Connection) -> list[tuple[str, dict[str, Any]]]:
    try:
        rows = conn.execute(
            "SELECT key, record_json FROM idempotency_records ORDER BY key ASC"
        ).fetchall()
    except sqlite3.Error as exc:
        raise IdempotencyInspectError("idempotency_db_read_error") from exc
    records: list[tuple[str, dict[str, Any]]] = []
    for key, raw in rows:
        records.append((str(key), json.loads(raw)))
    return records


def fetch_record(conn: sqlite3.Connection, key: str) -> dict[str, Any] | None:
    try:
        row = conn.execute(
            "SELECT record_json FROM idempotency_records WHERE key = ?",
            (key,),
        ).fetchone()
    except sqlite3.Error as exc:
        raise IdempotencyInspectError("idempotency_db_read_error") from exc
    if row is None:
        return None
    return json.loads(row[0])
