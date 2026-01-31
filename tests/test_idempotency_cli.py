from __future__ import annotations

from pathlib import Path
import json
import sqlite3

import pytest

from buff import cli as buff_cli


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


def _run_cli(args: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setattr(
        "sys.argv",
        ["buff"] + args,
    )
    try:
        buff_cli.main()
    except SystemExit as exc:
        return exc.code, capsys.readouterr()
    return 0, capsys.readouterr()


def test_list_empty_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    db_path = tmp_path / "idem.sqlite"
    _create_db(db_path)

    code, out = _run_cli(["idempotency", "list", "--db-path", str(db_path)], monkeypatch, capsys)
    assert code == 0
    assert out.out.strip().splitlines() == ["key\tstatus\treserved_at_utc\tage_seconds"]


def test_list_records_with_as_of(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
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

    code, out = _run_cli(
        [
            "idempotency",
            "list",
            "--db-path",
            str(db_path),
            "--as-of-utc",
            "2026-01-01T00:10:00Z",
        ],
        monkeypatch,
        capsys,
    )
    assert code == 0
    lines = out.out.strip().splitlines()
    assert lines[0] == "key\tstatus\treserved_at_utc\tage_seconds"
    assert lines[1].startswith("aaa\tINFLIGHT\t2026-01-01T00:00:00Z\t600")
    assert lines[2].startswith("bbb\tPROCESSED\t\tNA")


def test_show_existing_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
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

    code, out = _run_cli(
        ["idempotency", "show", "aaa", "--db-path", str(db_path)],
        monkeypatch,
        capsys,
    )
    assert code == 0
    payload = json.loads(out.out)
    assert payload["status"] == "INFLIGHT"
    assert payload["reserved_at_utc"] == "2026-01-01T00:00:00Z"


def test_show_missing_key_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    db_path = tmp_path / "idem.sqlite"
    _create_db(db_path)

    code, out = _run_cli(
        ["idempotency", "show", "missing", "--db-path", str(db_path)],
        monkeypatch,
        capsys,
    )
    assert code == 2
    assert "not found" in out.err


def test_export_is_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
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

    code1, out1 = _run_cli(
        ["idempotency", "export", "--db-path", str(db_path)], monkeypatch, capsys
    )
    code2, out2 = _run_cli(
        ["idempotency", "export", "--db-path", str(db_path)], monkeypatch, capsys
    )

    assert code1 == 0
    assert code2 == 0
    assert out1.out == out2.out
    lines = [line for line in out1.out.strip().splitlines() if line]
    assert json.loads(lines[0])["key"] == "aaa"
    assert json.loads(lines[1])["key"] == "bbb"


def test_db_missing_exits_nonzero(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    code, out = _run_cli(
        ["idempotency", "list", "--db-path", "missing.sqlite"], monkeypatch, capsys
    )
    assert code == 1
    assert "idempotency_db_not_found" in out.err
