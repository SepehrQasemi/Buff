from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from audit.bundle import BundleError, build_bundle


pytestmark = pytest.mark.unit


def _create_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS idempotency_records (
            key TEXT PRIMARY KEY,
            record_json TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _insert_record(path: Path, key: str, record: dict) -> None:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO idempotency_records (key, record_json) VALUES (?, ?)",
        (key, payload),
    )
    conn.commit()
    conn.close()


def _write_decision_records(dir_path: Path) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "decision_records_001.jsonl").write_text(
        json.dumps({"event_id": "1"}, sort_keys=True) + "\n", encoding="utf-8"
    )
    (dir_path / "decision_records_002.jsonl").write_text(
        json.dumps({"event_id": "2"}, sort_keys=True) + "\n", encoding="utf-8"
    )


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def test_dir_bundle_deterministic(tmp_path: Path) -> None:
    db_path = tmp_path / "idem.sqlite"
    _create_db(db_path)
    _insert_record(
        db_path,
        "aaa",
        {
            "status": "INFLIGHT",
            "first_seen_utc": "2026-01-01T00:00:00Z",
            "reserved_at_utc": "2026-01-01T00:00:00Z",
            "reservation_token": 1,
            "result": None,
        },
    )
    _insert_record(
        db_path,
        "bbb",
        {
            "status": "PROCESSED",
            "order_id": "paper-1",
            "timestamp_utc": "2026-01-01T00:00:10Z",
            "first_seen_utc": "2026-01-01T00:00:00Z",
            "audit_ref": None,
            "decision": {"action": "placed"},
            "result": {"action": "placed"},
        },
    )
    decision_dir = tmp_path / "records"
    _write_decision_records(decision_dir)

    out_a = tmp_path / "bundle_a"
    out_b = tmp_path / "bundle_b"

    build_bundle(
        out_path=out_a,
        fmt="dir",
        as_of_utc="2026-01-01T00:00:00Z",
        db_path=db_path,
        decision_records_path=decision_dir,
        include_logs=[],
    )
    build_bundle(
        out_path=out_b,
        fmt="dir",
        as_of_utc="2026-01-01T00:00:00Z",
        db_path=db_path,
        decision_records_path=decision_dir,
        include_logs=[],
    )

    files = [
        "metadata.json",
        "idempotency.jsonl",
        "decision_records_index.json",
        "checksums.txt",
    ]
    for name in files:
        assert _read_bytes(out_a / name) == _read_bytes(out_b / name)


def test_zip_bundle_deterministic(tmp_path: Path) -> None:
    db_path = tmp_path / "idem.sqlite"
    _create_db(db_path)
    _insert_record(
        db_path,
        "aaa",
        {
            "status": "INFLIGHT",
            "first_seen_utc": "2026-01-01T00:00:00Z",
            "reserved_at_utc": "2026-01-01T00:00:00Z",
            "reservation_token": 1,
            "result": None,
        },
    )
    decision_dir = tmp_path / "records"
    _write_decision_records(decision_dir)

    zip_a = tmp_path / "bundle_a.zip"
    zip_b = tmp_path / "bundle_b.zip"

    build_bundle(
        out_path=zip_a,
        fmt="zip",
        as_of_utc="2026-01-01T00:00:00Z",
        db_path=db_path,
        decision_records_path=decision_dir,
        include_logs=[],
    )
    build_bundle(
        out_path=zip_b,
        fmt="zip",
        as_of_utc="2026-01-01T00:00:00Z",
        db_path=db_path,
        decision_records_path=decision_dir,
        include_logs=[],
    )

    assert zip_a.read_bytes() == zip_b.read_bytes()


def test_bundle_fail_closed_missing_db(tmp_path: Path) -> None:
    decision_dir = tmp_path / "records"
    _write_decision_records(decision_dir)
    with pytest.raises(BundleError):
        build_bundle(
            out_path=tmp_path / "bundle",
            fmt="dir",
            as_of_utc="2026-01-01T00:00:00Z",
            db_path=tmp_path / "missing.sqlite",
            decision_records_path=decision_dir,
            include_logs=[],
        )


def test_bundle_fail_closed_missing_records(tmp_path: Path) -> None:
    db_path = tmp_path / "idem.sqlite"
    _create_db(db_path)
    with pytest.raises(BundleError):
        build_bundle(
            out_path=tmp_path / "bundle",
            fmt="dir",
            as_of_utc="2026-01-01T00:00:00Z",
            db_path=db_path,
            decision_records_path=tmp_path / "missing",
            include_logs=[],
        )


def test_bundle_fail_closed_corrupt_db(tmp_path: Path) -> None:
    db_path = tmp_path / "idem.sqlite"
    db_path.write_text("not a sqlite db", encoding="utf-8")
    decision_dir = tmp_path / "records"
    _write_decision_records(decision_dir)
    with pytest.raises(BundleError):
        build_bundle(
            out_path=tmp_path / "bundle",
            fmt="dir",
            as_of_utc="2026-01-01T00:00:00Z",
            db_path=db_path,
            decision_records_path=decision_dir,
            include_logs=[],
        )
