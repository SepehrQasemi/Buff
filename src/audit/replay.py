from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from audit.canonical_json import canonical_json, canonical_json_bytes
from audit.decision_record import (
    CodeVersion,
    DecisionRecord,
    Inputs,
    Outcome,
    RunContext,
    Selection,
)
from audit.decision_records import compute_market_state_hash, parse_json_line
from audit.snapshot import Snapshot
from risk.contracts import RiskInputs as RiskInputsContract
from risk.contracts import validate_risk_inputs
from risk.contracts import RiskConfig, RiskState as RiskStateMachine
from risk.state_machine import evaluate_risk
from risk.contracts import RiskState
from selector.records import selection_to_record
from selector.selector import select_strategy

_LAST_LOAD_ERRORS = 0


@dataclass(frozen=True)
class ReplayResult:
    total: int
    matched: int
    mismatched: int
    hash_mismatch: int
    errors: int


@dataclass(frozen=True)
class ReplayDiff:
    path: str
    expected: Any
    actual: Any


@dataclass(frozen=True)
class ReplayReport:
    matched: bool
    diffs: list[ReplayDiff]
    replay_record: DecisionRecord


@dataclass(frozen=True)
class ReplayConfig:
    feature_builder: Callable[[list[dict[str, Any]]], dict[str, Any]] | None = None
    run_context_override: RunContext | None = None
    code_version_override: CodeVersion | None = None
    ts_utc_override: str | None = None
    exclude_paths: set[str] | None = None


class ReplayMissingConfigError(RuntimeError):
    def __init__(self, path: str) -> None:
        super().__init__(f"Missing required config at {path}")
        self.path = path


class ReplayConfigMismatchError(RuntimeError):
    def __init__(self, path: str) -> None:
        super().__init__(f"Config mismatch at {path}")
        self.path = path


def load_decision_records(path: str) -> list[dict]:
    records: list[dict] = []
    errors = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = parse_json_line(line)
            if record.get("schema_version") != "dr.v1":
                raise ValueError("schema_version")
            required = {
                "run_id",
                "seq",
                "timeframe",
                "risk_state",
                "market_state",
                "market_state_hash",
                "selection",
            }
            if not required.issubset(record.keys()):
                raise ValueError("missing_required_fields")
            records.append(record)
        except Exception:
            errors += 1
    global _LAST_LOAD_ERRORS
    _LAST_LOAD_ERRORS = errors
    return records


def last_load_errors() -> int:
    return _LAST_LOAD_ERRORS


def normalize_selection(sel: dict) -> dict:
    return {
        "strategy_id": sel.get("strategy_id"),
        "rule_id": sel.get("rule_id"),
        "reason": sel.get("reason"),
        "inputs": sel.get("inputs", {}),
    }


def replay_verify(*, records_path: str, strict: bool = False) -> ReplayResult:
    _ = strict
    records = load_decision_records(records_path)
    errors = last_load_errors()

    total = len(records)
    matched = 0
    mismatched = 0
    hash_mismatch = 0
    details: list[dict] = []

    for record in records:
        expected_hash = record.get("market_state_hash")
        computed_hash = compute_market_state_hash(record.get("market_state", {}))
        if computed_hash != expected_hash:
            hash_mismatch += 1
            continue

        risk_state_raw = record.get("risk_state", "")
        if isinstance(risk_state_raw, str):
            try:
                risk_state = RiskState(risk_state_raw)
            except ValueError:
                risk_state = RiskState.RED
        else:
            risk_state = RiskState.RED

        out = select_strategy(record.get("market_state", {}), risk_state)
        expected = normalize_selection(record.get("selection", {}))
        got = normalize_selection(selection_to_record(out))
        if expected == got:
            matched += 1
        else:
            mismatched += 1
            if len(details) < 20:
                details.append(
                    {
                        "seq": record.get("seq"),
                        "expected": expected,
                        "got": got,
                    }
                )

    if details:
        print(json.dumps({"mismatches": details}, indent=2))

    return ReplayResult(
        total=total,
        matched=matched,
        mismatched=mismatched,
        hash_mismatch=hash_mismatch,
        errors=errors,
    )


def _normalize_selection(selection: dict[str, Any], risk_state: str) -> Selection:
    strategy_id = selection.get("strategy_id")
    reasons = selection.get("reasons")
    rules_fired = selection.get("rules_fired")
    if reasons is None:
        reason = selection.get("reason")
        reasons = [reason] if isinstance(reason, str) and reason else []
    if rules_fired is None:
        rule_id = selection.get("rule_id")
        rules_fired = [rule_id] if isinstance(rule_id, str) and rule_id else []

    selected = strategy_id is not None
    if risk_state == RiskState.RED.value:
        selected = False
        strategy_id = None
        status = "blocked"
    elif selected:
        status = "selected"
    else:
        status = "no_selection"

    return Selection(
        selected=selected,
        strategy_id=strategy_id,
        status=status,
        score=selection.get("score"),
        reasons=reasons or [],
        rules_fired=rules_fired or [],
    )


def _coerce_risk_state(value: str) -> RiskState:
    try:
        return RiskState(value)
    except ValueError:
        return RiskState.RED


def _build_market_features(
    record: DecisionRecord, snapshot: Snapshot | None, config: ReplayConfig
) -> dict[str, Any]:
    if snapshot is None:
        return record.inputs.market_features
    if snapshot.features is not None:
        return snapshot.features
    if snapshot.market_data is not None and config.feature_builder is not None:
        return config.feature_builder(snapshot.market_data)
    return record.inputs.market_features


def _evaluate_risk_state(
    record: DecisionRecord,
    snapshot: Snapshot | None,
    config: ReplayConfig,
) -> str:
    if snapshot is None or snapshot.risk_inputs is None:
        if record.inputs.risk_mode == "fact":
            return record.inputs.risk_state
        raise ReplayMissingConfigError("snapshot.risk_inputs")
    if record.inputs.risk_mode == "fact":
        return record.inputs.risk_state
    validated: RiskInputsContract = validate_risk_inputs(snapshot.risk_inputs)
    risk_config = _resolve_risk_config(record, snapshot)
    cfg = _build_risk_config(risk_config)
    decision = evaluate_risk(validated, cfg)
    return decision.state.value


def _outcome_from_selection(selection: Selection) -> Outcome:
    if selection.status == "blocked":
        return Outcome(decision="BLOCKED", allowed=False, notes=None)
    if selection.status == "selected":
        return Outcome(decision="SELECT", allowed=True, notes=None)
    return Outcome(decision="SKIP", allowed=True, notes=None)


def _diff_values(
    expected: Any,
    actual: Any,
    path: str,
    diffs: list[ReplayDiff],
    exclude_paths: set[str],
) -> None:
    if path in exclude_paths:
        return
    if isinstance(expected, dict) and isinstance(actual, dict):
        keys = sorted(set(expected.keys()) | set(actual.keys()))
        for key in keys:
            next_path = f"{path}.{key}" if path else str(key)
            _diff_values(
                expected.get(key),
                actual.get(key),
                next_path,
                diffs,
                exclude_paths,
            )
        return
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            diffs.append(ReplayDiff(path=path, expected=expected, actual=actual))
            return
        for idx, (exp, act) in enumerate(zip(expected, actual)):
            next_path = f"{path}[{idx}]"
            _diff_values(exp, act, next_path, diffs, exclude_paths)
        return
    if expected != actual:
        diffs.append(ReplayDiff(path=path, expected=expected, actual=actual))


def replay_equivalence(
    expected: dict[str, Any],
    actual: dict[str, Any],
    *,
    exclude_paths: Iterable[str] | None = None,
) -> list[ReplayDiff]:
    excluded = set(exclude_paths or [])
    diffs: list[ReplayDiff] = []
    _diff_values(expected, actual, "", diffs, excluded)
    return diffs


class ReplayRunner:
    def __init__(self, config: ReplayConfig | None = None) -> None:
        self._config = config or ReplayConfig()

    def replay(
        self,
        record: DecisionRecord,
        snapshot: Snapshot | None = None,
        *,
        strict_core: bool = False,
        strict_full: bool = False,
    ) -> ReplayReport:
        config = self._config
        market_features = _build_market_features(record, snapshot, config)
        risk_state = _evaluate_risk_state(record, snapshot, config)

        selector_state = select_strategy(market_features, _coerce_risk_state(risk_state))
        selection = _normalize_selection(selection_to_record(selector_state), risk_state)
        outcome = _outcome_from_selection(selection)

        if strict_full:
            run_context = record.run_context
            code_version = record.code_version
            ts_utc = record.ts_utc
        else:
            run_context = config.run_context_override or record.run_context
            code_version = config.code_version_override or record.code_version
            ts_utc = config.ts_utc_override or record.ts_utc

        selector_inputs = (
            snapshot.selector_inputs
            if snapshot is not None and snapshot.selector_inputs is not None
            else record.inputs.selector_inputs
        )

        replay_record = DecisionRecord(
            decision_id=record.decision_id,
            ts_utc=ts_utc,
            symbol=record.symbol,
            timeframe=record.timeframe,
            code_version=code_version,
            run_context=run_context,
            artifacts=record.artifacts,
            inputs=Inputs(
                market_features=market_features,
                risk_state=risk_state,
                selector_inputs=selector_inputs,
                config=record.inputs.config,
                risk_mode=record.inputs.risk_mode,
            ),
            selection=selection,
            outcome=outcome,
        )

        if strict_full:
            diffs = replay_equivalence(
                record._full_payload(),
                replay_record._full_payload(),
                exclude_paths=config.exclude_paths,
            )
            return ReplayReport(matched=not diffs, diffs=diffs, replay_record=replay_record)

        if strict_core:
            diffs = replay_equivalence(
                record._core_payload(),
                replay_record._core_payload(),
                exclude_paths=config.exclude_paths,
            )
            return ReplayReport(matched=not diffs, diffs=diffs, replay_record=replay_record)

        excluded = config.exclude_paths or {"hashes"}
        expected_core = record._core_payload()
        actual_core = replay_record._core_payload()
        if canonical_json_bytes(expected_core) == canonical_json_bytes(actual_core):
            return ReplayReport(matched=True, diffs=[], replay_record=replay_record)
        diffs = replay_equivalence(
            expected_core,
            actual_core,
            exclude_paths=excluded,
        )
        return ReplayReport(matched=not diffs, diffs=diffs, replay_record=replay_record)


def diff_to_json(diffs: list[ReplayDiff]) -> str:
    payload = [
        {"path": diff.path, "expected": diff.expected, "actual": diff.actual} for diff in diffs
    ]
    return canonical_json(payload)


def _resolve_risk_config(record: DecisionRecord, snapshot: Snapshot | None) -> Mapping[str, Any]:
    record_config = record.inputs.config.get("risk_config")
    snapshot_config = None
    if snapshot is not None and snapshot.config is not None:
        snapshot_config = snapshot.config.get("risk_config")

    if record_config is None and snapshot_config is None:
        raise ReplayMissingConfigError("inputs.config.risk_config or snapshot.config.risk_config")

    if record_config is not None and not isinstance(record_config, Mapping):
        raise ReplayMissingConfigError("inputs.config.risk_config")
    if snapshot_config is not None and not isinstance(snapshot_config, Mapping):
        raise ReplayMissingConfigError("snapshot.config.risk_config")

    if record_config is not None and snapshot_config is not None:
        if canonical_json_bytes(record_config) != canonical_json_bytes(snapshot_config):
            raise ReplayConfigMismatchError(
                "inputs.config.risk_config != snapshot.config.risk_config"
            )
        return record_config

    if record_config is not None:
        return record_config
    return snapshot_config  # type: ignore[return-value]


def _build_risk_config(config: Mapping[str, Any]) -> RiskConfig:
    if "missing_red" not in config:
        raise ReplayMissingConfigError("inputs.config.risk_config.missing_red")
    no_metrics = config.get("no_metrics_state", RiskStateMachine.YELLOW)
    if isinstance(no_metrics, str):
        no_metrics = RiskStateMachine(no_metrics)
    return RiskConfig(
        missing_red=config.get("missing_red"),
        atr_yellow=config.get("atr_yellow"),
        atr_red=config.get("atr_red"),
        rvol_yellow=config.get("rvol_yellow"),
        rvol_red=config.get("rvol_red"),
        no_metrics_state=no_metrics,
    )


def main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Replay a decision record and verify reproducibility."
    )
    parser.add_argument("--decision", required=True, help="Path to decision record JSON")
    parser.add_argument("--snapshot", required=False, help="Path to snapshot JSON")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Require core_hash match (strict-core).",
    )
    parser.add_argument(
        "--strict-full",
        action="store_true",
        help="Require content_hash match (strict-full).",
    )
    parser.add_argument(
        "--out",
        required=False,
        help="Output directory for replay record",
    )
    parser.add_argument(
        "--json",
        required=False,
        help="Write diff JSON to file on mismatch",
    )
    args = parser.parse_args()
    if args.strict and args.strict_full:
        print("ERROR: --strict and --strict-full are mutually exclusive", file=sys.stderr)
        sys.exit(2)

    decision_payload = json.loads(Path(args.decision).read_text(encoding="utf-8"))
    decision = DecisionRecord.from_dict(decision_payload)

    snapshot = None
    if args.snapshot:
        snapshot = Snapshot.from_dict(json.loads(Path(args.snapshot).read_text(encoding="utf-8")))

    runner = ReplayRunner()
    try:
        report = runner.replay(
            decision,
            snapshot,
            strict_core=args.strict,
            strict_full=args.strict_full,
        )
    except (ReplayMissingConfigError, ReplayConfigMismatchError) as exc:
        print(f"REPLAY_ERROR {exc}", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"REPLAY_ERROR unexpected: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.out:
        out_dir = Path(args.out)
        if out_dir.suffix.lower() == ".json":
            print("ERROR: --out must be a directory", file=sys.stderr)
            sys.exit(2)
        if out_dir.exists() and out_dir.is_file():
            print("ERROR: --out must be a directory", file=sys.stderr)
            sys.exit(2)
    else:
        out_dir = Path("artifacts") / "replays"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"replay_{decision.decision_id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report.replay_record.to_canonical_json(), encoding="utf-8")

    if report.matched:
        if args.strict_full:
            print("REPLAY_OK strict-full")
        elif args.strict:
            print("REPLAY_OK strict-core")
        else:
            print("REPLAY_OK non-strict")
        return

    print("REPLAY_MISMATCH")
    diff_json = diff_to_json(report.diffs)
    print(diff_json)
    if args.json:
        diff_path = Path(args.json)
        diff_path.parent.mkdir(parents=True, exist_ok=True)
        diff_path.write_text(diff_json, encoding="utf-8")
    sys.exit(2)


if __name__ == "__main__":
    main()
