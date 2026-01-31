from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from audit.schema import canonical_json


SCHEMA_VERSION = 1


def default_idempotency_db_path() -> Path:
    override = os.getenv("BUFF_IDEMPOTENCY_DB_PATH")
    if override:
        return Path(override)
    return Path("workspaces") / "idempotency.sqlite"


class SQLiteIdempotencyStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        self._ensure_schema(conn)
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS idempotency_records (
                key TEXT PRIMARY KEY,
                record_json TEXT NOT NULL
            )
            """
        )
        version = conn.execute("PRAGMA user_version").fetchone()
        current = int(version[0]) if version else 0
        if current == 0:
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        elif current != SCHEMA_VERSION:
            raise ValueError("unsupported_schema_version")

    def has(self, key: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM idempotency_records WHERE key = ? LIMIT 1", (key,)
            ).fetchone()
        return row is not None

    def get(self, key: str) -> Mapping[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT record_json FROM idempotency_records WHERE key = ?",
                (key,),
            ).fetchone()
        if row is None:
            raise KeyError(key)
        return json.loads(row[0])

    def put(self, key: str, record: Mapping[str, Any]) -> None:
        payload = canonical_json(record)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO idempotency_records (key, record_json) VALUES (?, ?)",
                (key, payload),
            )
