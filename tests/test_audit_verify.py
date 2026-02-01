from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from audit.bundle import build_bundle
from audit.verify import verify_bundle
from tests.test_audit_bundle import _create_db, _insert_record, _write_decision_records


pytestmark = pytest.mark.unit


def _setup_bundle(tmp_path: Path, fmt: str) -> Path:
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
    out_path = tmp_path / ("bundle.zip" if fmt == "zip" else "bundle_dir")
    build_bundle(
        out_path=out_path,
        fmt=fmt,
        as_of_utc="2026-01-01T00:00:00Z",
        db_path=db_path,
        decision_records_path=decision_dir,
        include_logs=[],
    )
    return out_path


def test_verify_valid_dir_bundle(tmp_path: Path) -> None:
    bundle_path = _setup_bundle(tmp_path, "dir")
    report = verify_bundle(path=bundle_path, fmt="dir")
    assert report["ok"]


def test_verify_valid_zip_bundle(tmp_path: Path) -> None:
    bundle_path = _setup_bundle(tmp_path, "zip")
    report = verify_bundle(path=bundle_path, fmt="zip")
    assert report["ok"]


def test_tamper_checksums_detected_dir(tmp_path: Path) -> None:
    bundle_path = _setup_bundle(tmp_path, "dir")
    idempo_path = bundle_path / "idempotency.jsonl"
    idempo_path.write_text("tampered\n", encoding="utf-8")
    report = verify_bundle(path=bundle_path, fmt="dir")
    assert not report["ok"]
    assert any(err["code"] == "checksums_mismatch" for err in report["errors"])


def test_missing_required_file(tmp_path: Path) -> None:
    bundle_path = _setup_bundle(tmp_path, "dir")
    (bundle_path / "decision_records_index.json").unlink()
    report = verify_bundle(path=bundle_path, fmt="dir")
    assert not report["ok"]
    assert any(err["code"] == "required_missing" for err in report["errors"])


def test_index_mismatch_detected(tmp_path: Path) -> None:
    bundle_path = _setup_bundle(tmp_path, "dir")
    index_path = bundle_path / "decision_records_index.json"
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    payload["files"][0]["line_count"] = 999
    index_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    report = verify_bundle(path=bundle_path, fmt="dir")
    assert not report["ok"]
    assert any(err["code"] == "index_line_count_mismatch" for err in report["errors"])


def test_idempotency_invalid_json(tmp_path: Path) -> None:
    bundle_path = _setup_bundle(tmp_path, "dir")
    idempo_path = bundle_path / "idempotency.jsonl"
    idempo_path.write_text("{invalid}\n", encoding="utf-8")
    report = verify_bundle(path=bundle_path, fmt="dir")
    assert not report["ok"]
    assert any(err["code"] == "idempotency_invalid_json" for err in report["errors"])


def test_strict_ordering_failures(tmp_path: Path) -> None:
    bundle_path = _setup_bundle(tmp_path, "dir")
    checksums_path = bundle_path / "checksums.txt"
    lines = checksums_path.read_text(encoding="utf-8").splitlines()
    checksums_path.write_text("\n".join(reversed(lines)) + "\n", encoding="utf-8")
    report = verify_bundle(path=bundle_path, fmt="dir", strict=False)
    assert report["ok"]
    report_strict = verify_bundle(path=bundle_path, fmt="dir", strict=True)
    assert not report_strict["ok"]


def test_tamper_zip_checksums(tmp_path: Path) -> None:
    bundle_path = _setup_bundle(tmp_path, "zip")
    tampered_zip = tmp_path / "bundle_tampered.zip"
    with zipfile.ZipFile(bundle_path, "r") as src, zipfile.ZipFile(tampered_zip, "w") as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "checksums.txt":
                data = b"deadbeef  metadata.json\n"
            dst.writestr(info, data)
    bundle_path = tampered_zip
    report = verify_bundle(path=bundle_path, fmt="zip")
    assert not report["ok"]
