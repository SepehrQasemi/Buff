from __future__ import annotations

import json
from pathlib import Path

import pytest

from audit.migrate_records import migrate_file, migrate_record_dict


def test_migration_idempotent(tmp_path: Path) -> None:
    src = Path("tests/fixtures/legacy_records/legacy_fact.json")
    out_dir = tmp_path / "out"
    report = migrate_file(src, out_dir, dry_run=False)
    assert report.errors == 0

    migrated_path = out_dir / src.name
    migrated = json.loads(migrated_path.read_text(encoding="utf-8"))

    second = migrate_record_dict(migrated)
    assert "hashes" not in second
    report_second = migrate_file(migrated_path, out_dir, dry_run=True)
    assert report_second.errors == 0


def test_migration_adds_risk_mode_fact_when_no_risk_inputs() -> None:
    src = Path("tests/fixtures/legacy_records/legacy_fact.json")
    original = json.loads(src.read_text(encoding="utf-8"))
    migrated = migrate_record_dict(original)
    assert migrated["inputs"]["risk_mode"] == "fact"


def test_migration_adds_risk_mode_computed_when_snapshot_risk_inputs_present() -> None:
    src = Path("tests/fixtures/legacy_records/legacy_computed_with_snapshot.json")
    original = json.loads(src.read_text(encoding="utf-8"))
    migrated = migrate_record_dict(original)
    assert migrated["inputs"]["risk_mode"] == "computed"


def test_migration_fails_on_missing_config_for_computed_mode(tmp_path: Path) -> None:
    src = Path("tests/fixtures/legacy_records/legacy_computed_missing_config.json")
    report = migrate_file(src, tmp_path, dry_run=True)
    assert report.errors == 1
    assert report.entries[0].errors


def test_migration_preserves_selection_outcome_semantics() -> None:
    src = Path("tests/fixtures/legacy_records/legacy_computed_with_snapshot.json")
    original = json.loads(src.read_text(encoding="utf-8"))
    migrated = migrate_record_dict(original)
    assert migrated["selection"]["strategy_id"] == original["selection"]["strategy_id"]
    assert migrated["outcome"] == original["outcome"]


def test_migration_fills_empty_strategy_id_from_strategy_ref() -> None:
    src = Path("tests/fixtures/legacy_records/legacy_fact.json")
    original = json.loads(src.read_text(encoding="utf-8"))
    original["selection"]["strategy_id"] = ""
    original["strategy"] = {"name": "trend", "version": "1.0.0"}
    original["selection"].pop("selected", None)
    original["selection"].pop("status", None)

    migrated = migrate_record_dict(original)
    assert migrated["selection"]["strategy_id"] == "trend@1.0.0"
    assert migrated["selection"]["selected"] is True
    assert migrated["selection"]["status"] == "selected"


def test_migration_empty_strategy_id_missing_strategy_fails() -> None:
    src = Path("tests/fixtures/legacy_records/legacy_fact.json")
    original = json.loads(src.read_text(encoding="utf-8"))
    original["selection"]["strategy_id"] = ""
    original["selection"].pop("selected", None)
    original["selection"].pop("status", None)

    with pytest.raises(ValueError, match="empty_strategy_id_missing_strategy"):
        migrate_record_dict(original)


def test_cli_migrate_dry_run_no_write(tmp_path: Path) -> None:
    src = Path("tests/fixtures/legacy_records/legacy_fact.json")
    report = migrate_file(src, tmp_path, dry_run=True)
    assert report.errors == 0
    assert not (tmp_path / src.name).exists()
