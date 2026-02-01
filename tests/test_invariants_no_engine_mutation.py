from __future__ import annotations

import ast
from pathlib import Path

import pytest

from audit import decision_records
from audit.run import AuditRunError, run_audit
from audit.bundle import build_bundle
from buff.features.metadata import sha256_file
from tests.test_audit_bundle import _create_db


pytestmark = pytest.mark.unit


def _run_source() -> str:
    return Path("src/audit/run.py").read_text(encoding="utf-8")


def _has_decision_records_attribute_assignment(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            else:
                targets = [node.target]
            for target in targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                    if target.value.id == "decision_records":
                        return True
    return False


def test_audit_run_source_has_no_decision_records_patching() -> None:
    source = _run_source()
    forbidden_substrings = [
        "decision_records._utc_timestamp",
        "decision_records.DecisionRecordWriter",
        "monkeypatch",
        "patch(",
    ]
    for token in forbidden_substrings:
        assert token not in source, f"Forbidden token in audit.run: {token}"

    tree = ast.parse(source)
    assert not _has_decision_records_attribute_assignment(tree), (
        "audit.run must not assign attributes on audit.decision_records"
    )


def test_run_audit_does_not_patch_decision_records_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_ts = decision_records._utc_timestamp
    original_writer = decision_records.DecisionRecordWriter

    def _boom(*_args, **_kwargs):
        raise RuntimeError("exec_failed")

    monkeypatch.setattr("audit.run.run_paper_smoke", _boom)

    with pytest.raises(AuditRunError):
        run_audit(
            seed=1,
            out_path=tmp_path / "bundle_dir",
            as_of_utc="2026-01-01T00:00:00Z",
            config_path=None,
            decision_records_dir=tmp_path / "runs",
            fmt="dir",
            verify=False,
            db_path=tmp_path / "idem.sqlite",
        )

    assert decision_records._utc_timestamp is original_ts
    assert decision_records.DecisionRecordWriter is original_writer


def test_as_of_utc_not_passed_into_execution() -> None:
    source = _run_source()
    tree = ast.parse(source)
    run_paper_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run_paper_smoke"
    ]
    assert run_paper_calls, "run_paper_smoke call not found in audit.run"
    for call in run_paper_calls:
        assert not call.keywords, "run_paper_smoke must not receive keyword args"


def test_bundle_is_read_only_for_idempotency_db(tmp_path: Path) -> None:
    db_path = tmp_path / "idem.sqlite"
    _create_db(db_path)

    records_dir = tmp_path / "runs"
    records_dir.mkdir(parents=True, exist_ok=True)
    (records_dir / "decision_records_0000.jsonl").write_text(
        '{"ts_utc":"2026-01-01T00:00:00Z","event":"noop"}\n', encoding="utf-8"
    )

    out_path = tmp_path / "bundle_dir"
    before_hash = sha256_file(db_path)

    build_bundle(
        out_path=out_path,
        fmt="dir",
        as_of_utc=None,
        db_path=db_path,
        decision_records_path=records_dir,
        include_logs=[],
    )

    after_hash = sha256_file(db_path)
    assert before_hash == after_hash
