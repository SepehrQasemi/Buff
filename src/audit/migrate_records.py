from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from audit.canonical_json import canonical_json_bytes
from audit.decision_record import DecisionRecord


@dataclass(frozen=True)
class MigrationEntry:
    path: str
    changed: bool
    before_hashes: dict[str, str | None]
    after_hashes: dict[str, str | None]
    actions: list[str]
    errors: list[str]


@dataclass(frozen=True)
class MigrationReport:
    entries: list[MigrationEntry]
    changed: int
    errors: int


def _load_json(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("record must be a JSON object")
    return payload


def _snapshot_risk_inputs(record: dict[str, Any]) -> dict[str, Any] | None:
    snapshot = record.get("snapshot")
    if isinstance(snapshot, dict):
        risk_inputs = snapshot.get("risk_inputs")
        if isinstance(risk_inputs, dict):
            return risk_inputs
    risk_inputs = record.get("risk_inputs")
    if isinstance(risk_inputs, dict):
        return risk_inputs
    return None


def _snapshot_risk_config(record: dict[str, Any]) -> dict[str, Any] | None:
    snapshot = record.get("snapshot")
    if isinstance(snapshot, dict):
        config = snapshot.get("config")
        if isinstance(config, dict):
            risk_config = config.get("risk_config")
            if isinstance(risk_config, dict):
                return risk_config
    return None


def migrate_record_dict(d: dict[str, Any]) -> dict[str, Any]:
    record = json.loads(json.dumps(d))
    inputs = record.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("inputs must be a dict")

    selection = record.get("selection")
    if not isinstance(selection, dict):
        raise ValueError("selection must be a dict")

    actions: list[str] = []

    if "selected" not in selection or "status" not in selection:
        strategy_id = selection.get("strategy_id")
        if strategy_id is None:
            selection["selected"] = False
            selection["status"] = "no_selection"
            selection["strategy_id"] = None
        else:
            selection["selected"] = True
            selection["status"] = "selected"
        actions.append("migrate_selection_schema")

    if "config" not in inputs or not isinstance(inputs.get("config"), dict):
        inputs["config"] = {}
        actions.append("add_inputs_config")

    if "risk_mode" not in inputs:
        risk_inputs = _snapshot_risk_inputs(record)
        if risk_inputs is not None:
            inputs["risk_mode"] = "computed"
        else:
            inputs["risk_mode"] = "fact"
        actions.append("add_risk_mode")

    record["inputs"] = inputs
    record["selection"] = selection

    record.pop("hashes", None)
    return record


def _ensure_replayable(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    inputs = record.get("inputs", {})
    risk_mode = inputs.get("risk_mode")
    if risk_mode == "computed":
        record_config = None
        snapshot_config = None
        if isinstance(inputs.get("config"), dict):
            record_config = inputs["config"].get("risk_config")
        snapshot_config = _snapshot_risk_config(record)
        if record_config is None and snapshot_config is None:
            errors.append("$.inputs.config.risk_config or $.snapshot.config.risk_config missing")
        elif record_config is not None and snapshot_config is not None:
            if canonical_json_bytes(record_config) != canonical_json_bytes(snapshot_config):
                errors.append("$.inputs.config.risk_config != $.snapshot.config.risk_config")
    return errors


def _hashes_from_record(record: dict[str, Any]) -> dict[str, str | None]:
    hashes = record.get("hashes")
    if not isinstance(hashes, dict):
        return {"core_hash": None, "content_hash": None}
    return {
        "core_hash": hashes.get("core_hash"),
        "content_hash": hashes.get("content_hash"),
    }


def migrate_file(
    path_in: Path,
    path_out: Path | None,
    dry_run: bool,
    *,
    allow_nonreplayable: bool = False,
) -> MigrationReport:
    entries: list[MigrationEntry] = []
    errors = 0
    changed = 0

    paths: list[Path] = []
    if path_in.is_dir():
        paths = sorted([p for p in path_in.rglob("*.json") if p.is_file()])
    else:
        paths = [path_in]

    for path in paths:
        actions: list[str] = []
        entry_errors: list[str] = []
        try:
            original = _load_json(path)
            before_hashes = _hashes_from_record(original)
            migrated = migrate_record_dict(original)

            replay_errors = _ensure_replayable(migrated)
            if replay_errors:
                entry_errors.extend(replay_errors)
                if not allow_nonreplayable:
                    errors += 1
            if replay_errors:
                actions.append("not_replayable")

            record_obj = DecisionRecord.from_dict(migrated)
            migrated_out = record_obj.to_dict()
            actions.append("recompute_hashes")

            changed_flag = migrated_out != original
            if changed_flag:
                changed += 1

            if not dry_run and (path_out is not None or path_in.is_file()):
                if path_out is None:
                    target = path
                else:
                    rel = path.relative_to(path_in) if path_in.is_dir() else path.name
                    target = path_out / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                temp_path = target.with_suffix(target.suffix + ".tmp")
                temp_path.write_text(json.dumps(migrated_out, ensure_ascii=False), encoding="utf-8")
                os.replace(temp_path, target)

            entries.append(
                MigrationEntry(
                    path=str(path),
                    changed=changed_flag,
                    before_hashes=before_hashes,
                    after_hashes={
                        "core_hash": migrated_out["hashes"]["core_hash"],
                        "content_hash": migrated_out["hashes"]["content_hash"],
                    },
                    actions=actions,
                    errors=entry_errors,
                )
            )
        except Exception as exc:
            errors += 1
            entries.append(
                MigrationEntry(
                    path=str(path),
                    changed=False,
                    before_hashes={"core_hash": None, "content_hash": None},
                    after_hashes={"core_hash": None, "content_hash": None},
                    actions=actions,
                    errors=[str(exc)],
                )
            )

    return MigrationReport(entries=entries, changed=changed, errors=errors)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy decision records.")
    parser.add_argument("--in", dest="path_in", required=True, help="Input file or directory")
    parser.add_argument("--out", dest="path_out", required=False, help="Output directory")
    parser.add_argument("--in-place", action="store_true", help="Overwrite inputs in place")
    parser.add_argument("--dry-run", action="store_true", help="Do not write changes")
    parser.add_argument(
        "--allow-nonreplayable",
        action="store_true",
        help="Allow non-replayable records without exiting 2",
    )
    args = parser.parse_args()

    path_in = Path(args.path_in)
    path_out = Path(args.path_out) if args.path_out else None

    if not path_in.exists():
        print("ERROR: input path does not exist", file=sys.stderr)
        sys.exit(2)
    if args.in_place and path_out is not None:
        print("ERROR: --in-place and --out are mutually exclusive", file=sys.stderr)
        sys.exit(2)
    if not args.in_place and path_out is None:
        path_out = None

    report = migrate_file(
        path_in,
        path_out,
        args.dry_run,
        allow_nonreplayable=args.allow_nonreplayable,
    )

    payload = {
        "changed": report.changed,
        "errors": report.errors,
        "entries": [
            {
                "path": entry.path,
                "changed": entry.changed,
                "before_hashes": entry.before_hashes,
                "after_hashes": entry.after_hashes,
                "actions": entry.actions,
                "errors": entry.errors,
            }
            for entry in report.entries
        ],
    }
    print(json.dumps(payload, ensure_ascii=False))

    if report.errors:
        sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"ERROR: unexpected: {exc}", file=sys.stderr)
        sys.exit(1)
