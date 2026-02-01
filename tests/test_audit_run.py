from __future__ import annotations

from pathlib import Path

import pytest

from audit.run import AuditRunError, run_audit
from audit.verify import verify_bundle
from tests.test_audit_bundle import _create_db


pytestmark = pytest.mark.unit


def _empty_db(path: Path) -> None:
    _create_db(path)


def test_audit_run_happy_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "idem.sqlite"
    _empty_db(db_path)
    out_path = tmp_path / "bundle_dir"
    decision_dir = tmp_path / "runs"

    result = run_audit(
        seed=123,
        out_path=out_path,
        as_of_utc="2026-01-01T00:00:00Z",
        config_path=None,
        decision_records_dir=decision_dir,
        fmt="dir",
        verify=True,
        db_path=db_path,
    )

    assert result.ok
    assert out_path.exists()
    report = verify_bundle(path=out_path, fmt="dir", strict=False, as_of_utc="2026-01-01T00:00:00Z")
    assert report["ok"]


def test_audit_run_verification_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "idem.sqlite"
    _empty_db(db_path)
    out_path = tmp_path / "bundle_dir"
    decision_dir = tmp_path / "runs"

    def _fail_verify(*_args, **_kwargs):
        return {"ok": False, "errors": []}

    monkeypatch.setattr("audit.run.verify_bundle", _fail_verify)

    with pytest.raises(AuditRunError):
        run_audit(
            seed=123,
            out_path=out_path,
            as_of_utc="2026-01-01T00:00:00Z",
            config_path=None,
            decision_records_dir=decision_dir,
            fmt="dir",
            verify=True,
            db_path=db_path,
        )


def test_audit_run_determinism(tmp_path: Path) -> None:
    db_path = tmp_path / "idem.sqlite"
    _empty_db(db_path)
    decision_dir = tmp_path / "runs"
    out_a = tmp_path / "bundle_a"
    out_b = tmp_path / "bundle_b"

    result_a = run_audit(
        seed=7,
        out_path=out_a,
        as_of_utc="2026-01-01T00:00:00Z",
        config_path=None,
        decision_records_dir=decision_dir,
        fmt="dir",
        verify=True,
        db_path=db_path,
    )
    assert result_a.ok

    # clean decision records dir to avoid appends
    if decision_dir.exists():
        for path in sorted(decision_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()

    result_b = run_audit(
        seed=7,
        out_path=out_b,
        as_of_utc="2026-01-01T00:00:00Z",
        config_path=None,
        decision_records_dir=decision_dir,
        fmt="dir",
        verify=True,
        db_path=db_path,
    )
    assert result_b.ok

    idempotency_a = (out_a / "idempotency.jsonl").read_bytes()
    idempotency_b = (out_b / "idempotency.jsonl").read_bytes()
    assert idempotency_a == idempotency_b


def test_audit_run_fail_closed_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "idem.sqlite"
    _empty_db(db_path)
    out_path = tmp_path / "bundle_dir"
    decision_dir = tmp_path / "runs"

    def _boom(*_args, **_kwargs):
        raise RuntimeError("exec_failed")

    def _should_not_call(*_args, **_kwargs):
        raise AssertionError("bundle_called")

    monkeypatch.setattr("audit.run.run_paper_smoke", _boom)
    monkeypatch.setattr("audit.run.build_bundle", _should_not_call)

    with pytest.raises(AuditRunError):
        run_audit(
            seed=1,
            out_path=out_path,
            as_of_utc="2026-01-01T00:00:00Z",
            config_path=None,
            decision_records_dir=decision_dir,
            fmt="dir",
            verify=True,
            db_path=db_path,
        )
