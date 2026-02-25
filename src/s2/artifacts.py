from __future__ import annotations

import csv
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from .canonical import (
    build_pack_root_hash,
    NUMERIC_POLICY,
    NUMERIC_POLICY_DIGEST_SHA256,
    NUMERIC_POLICY_ID,
    canonical_json_bytes,
    canonicalize_artifact_path,
    canonicalize_timestamp_utc,
    contains_forbidden_path_token,
    sha256_hex_bytes,
    sha256_hex_file,
    stable_sort_records,
    validate_utf8_lf_bytes,
    write_canonical_json,
    write_canonical_jsonl,
)
from .core import (
    DECISION_RECORD_SCHEMA,
    FUNDING_TRANSFER_SCHEMA,
    POSITION_TIMELINE_SCHEMA,
    RISK_EVENT_SCHEMA,
    SIMULATED_FILL_SCHEMA,
    SIMULATED_ORDER_SCHEMA,
    S2CoreConfig,
    S2CoreError,
    run_s2_core_loop,
)
from .failure import (
    ALLOWED_ERROR_CODES,
    RUN_FAILURE_SCHEMA_VERSION,
    S2StructuredFailure,
    build_run_failure_payload,
    deterministic_failure_timestamp,
)
from .models import FundingDataMissingError, PositionInvariantError


PAPER_RUN_MANIFEST_SCHEMA = "s2/paper_run_manifest/v1"
COST_BREAKDOWN_SCHEMA = "s2/cost_breakdown/v1"
ARTIFACT_PACK_MANIFEST_SCHEMA = "s2/artifact_pack_manifest/v1"
RUN_DIGESTS_SCHEMA = "s2/run_digests/v1"
RUN_FAILURE_SCHEMA = RUN_FAILURE_SCHEMA_VERSION
RUN_STATUS_SUCCEEDED = "SUCCEEDED"
RUN_STATUS_FAILED = "FAILED"

REQUIRED_ARTIFACTS = (
    "paper_run_manifest.json",
    "decision_records.jsonl",
    "simulated_orders.jsonl",
    "simulated_fills.jsonl",
    "position_timeline.jsonl",
    "risk_events.jsonl",
    "funding_transfers.jsonl",
    "cost_breakdown.json",
    "artifact_pack_manifest.json",
    "run_digests.json",
)

REQUIRED_FAILURE_ARTIFACTS = (
    "paper_run_manifest.json",
    "risk_events.jsonl",
    "run_failure.json",
    "artifact_pack_manifest.json",
    "run_digests.json",
)

PACK_HASH_EXCLUDED_ARTIFACTS = frozenset({"artifact_pack_manifest.json", "run_digests.json"})
JSONL_ARTIFACTS = (
    "decision_records.jsonl",
    "simulated_orders.jsonl",
    "simulated_fills.jsonl",
    "position_timeline.jsonl",
    "risk_events.jsonl",
    "funding_transfers.jsonl",
)

JSONL_SCHEMAS = {
    "decision_records.jsonl": DECISION_RECORD_SCHEMA,
    "simulated_orders.jsonl": SIMULATED_ORDER_SCHEMA,
    "simulated_fills.jsonl": SIMULATED_FILL_SCHEMA,
    "position_timeline.jsonl": POSITION_TIMELINE_SCHEMA,
    "risk_events.jsonl": RISK_EVENT_SCHEMA,
    "funding_transfers.jsonl": FUNDING_TRANSFER_SCHEMA,
}

JSONL_SORT_KEYS = {
    "decision_records.jsonl": ("event_seq", "ts_utc", "decision", "seed"),
    "simulated_orders.jsonl": ("event_seq", "order_id", "symbol", "side"),
    "simulated_fills.jsonl": ("event_seq", "fill_id", "order_id", "side"),
    "position_timeline.jsonl": ("event_seq", "ts_utc", "mark_price"),
    "risk_events.jsonl": ("event_seq", "ts_utc", "reason_code", "detail"),
    "funding_transfers.jsonl": (
        "event_seq",
        "ts_utc",
        "funding_rate",
        "position_qty",
        "mark_price",
    ),
}

JSONL_REQUIRED_FIELDS = {
    "decision_records.jsonl": {
        "schema_version",
        "numeric_policy_id",
        "event_seq",
        "ts_utc",
        "decision",
        "decision_time",
        "seed",
    },
    "simulated_orders.jsonl": {
        "schema_version",
        "numeric_policy_id",
        "order_id",
        "event_seq",
        "ts_utc",
        "symbol",
        "side",
        "qty",
        "decision",
        "order_type",
    },
    "simulated_fills.jsonl": {
        "schema_version",
        "numeric_policy_id",
        "fill_id",
        "order_id",
        "event_seq",
        "ts_utc",
        "symbol",
        "side",
        "qty",
        "fill_price",
        "reference_price",
        "fee_quote",
        "slippage_quote",
        "realized_pnl_delta_quote",
    },
    "position_timeline.jsonl": {
        "schema_version",
        "numeric_policy_id",
        "event_seq",
        "ts_utc",
        "mark_price",
        "position_qty",
        "avg_entry_price",
        "realized_pnl_quote",
        "unrealized_pnl_quote",
        "cash_balance_quote",
        "equity_quote",
        "invariants_ok",
    },
    "risk_events.jsonl": {
        "schema_version",
        "numeric_policy_id",
        "event_seq",
        "ts_utc",
        "reason_code",
        "detail",
    },
    "funding_transfers.jsonl": {
        "schema_version",
        "numeric_policy_id",
        "event_seq",
        "ts_utc",
        "funding_rate",
        "position_qty",
        "mark_price",
        "transfer_quote",
    },
}

JSON_SCHEMAS = {
    "paper_run_manifest.json": PAPER_RUN_MANIFEST_SCHEMA,
    "cost_breakdown.json": COST_BREAKDOWN_SCHEMA,
    "artifact_pack_manifest.json": ARTIFACT_PACK_MANIFEST_SCHEMA,
    "run_digests.json": RUN_DIGESTS_SCHEMA,
    "run_failure.json": RUN_FAILURE_SCHEMA,
}

_RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


class S2ArtifactError(RuntimeError):
    def __init__(self, code: str, message: str, details: Mapping[str, Any] | None = None):
        self.code = code
        self.details = dict(details or {})
        super().__init__(f"{code}:{message}")

    def to_payload(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "details": dict(self.details)}


@dataclass(frozen=True)
class S2ArtifactRequest:
    run_id: str
    symbol: str
    timeframe: str
    seed: int
    data_path: str
    strategy_version: str
    data_sha256: str | None = None
    strategy_config: Mapping[str, Any] = field(default_factory=dict)
    risk_version: str = "risk.v1"
    risk_config: Mapping[str, Any] = field(default_factory=dict)
    core_config: S2CoreConfig = field(default_factory=S2CoreConfig)


def _normalize_run_id(run_id: str) -> str:
    text = str(run_id).strip().lower()
    if not _RUN_ID_RE.fullmatch(text):
        raise S2ArtifactError("INPUT_INVALID", "run_id format invalid", {"field": "run_id"})
    return text


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _require_nonempty(value: str, field: str) -> str:
    text = str(value).strip()
    if not text:
        raise S2ArtifactError("INPUT_MISSING", f"{field} is required", {"field": field})
    return text


def _load_bars_from_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise S2ArtifactError("INPUT_MISSING", "critical input missing", {"field": "data_path"})
    if not path.is_file():
        raise S2ArtifactError("INPUT_INVALID", "data_path must be a file", {"field": "data_path"})

    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
    except OSError as exc:
        raise S2ArtifactError(
            "INPUT_INVALID", "failed to read data_path", {"error": str(exc), "field": "data_path"}
        ) from exc

    if not rows:
        raise S2ArtifactError(
            "INPUT_MISSING", "critical input data is empty", {"field": "data_path"}
        )

    bars: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        try:
            ts = str(row.get("timestamp") or row.get("ts_utc") or "").strip()
            if not ts:
                raise ValueError("missing timestamp")
            bars.append(
                {
                    "ts_utc": canonicalize_timestamp_utc(ts),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume") or 0.0),
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise S2ArtifactError(
                "SCHEMA_INVALID",
                "data row schema invalid",
                {"field": "data_path", "row_index": idx},
            ) from exc
    return bars


def _strategy_fn_from_config(config: Mapping[str, Any]):
    raw_actions = config.get("actions", [])
    actions: list[str] = []
    if isinstance(raw_actions, list):
        actions = [str(item).strip().upper() for item in raw_actions]

    def _fn(event, state, rng):
        del state, rng
        if event.seq < len(actions):
            return actions[event.seq]
        return "HOLD"

    return _fn


def _risk_fn_from_config(config: Mapping[str, Any]):
    raw_blocked = config.get("blocked_event_seqs", [])
    blocked: set[int] = set()
    if isinstance(raw_blocked, list):
        for item in raw_blocked:
            try:
                blocked.add(int(item))
            except (TypeError, ValueError):
                continue

    def _fn(event, state, action, rng):
        del state, action, rng
        if event.seq in blocked:
            return False, "risk_blocked_by_config"
        return True, None

    return _fn


def _bars_payload(bars: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "ts_utc": str(row["ts_utc"]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        }
        for row in bars
    ]


def _manifest_payload(
    request: S2ArtifactRequest,
    *,
    data_file_sha256: str,
    bars_sha256: str,
    strategy_config_digest: str,
    risk_config_digest: str,
    replay_tuple: list[Any],
    replay_digest: str,
    artifacts: tuple[str, ...],
    run_status: str,
) -> dict[str, Any]:
    data_ref = canonicalize_artifact_path(request.data_path, repo_root=_repo_root())
    return {
        "schema_version": PAPER_RUN_MANIFEST_SCHEMA,
        "numeric_policy_id": NUMERIC_POLICY_ID,
        "numeric_policy": dict(NUMERIC_POLICY),
        "run_id": request.run_id,
        "run_status": run_status,
        "symbol": request.symbol,
        "timeframe": request.timeframe,
        "strategy": {
            "version": request.strategy_version,
            "config_digest_sha256": strategy_config_digest,
            "config": dict(request.strategy_config),
        },
        "risk": {
            "version": request.risk_version,
            "config_digest_sha256": risk_config_digest,
            "config": dict(request.risk_config),
            "hard_caps": {
                "max_leverage": float(request.core_config.risk_caps.max_leverage),
                "max_position_notional_quote": float(
                    request.core_config.risk_caps.max_position_notional_quote
                ),
                "max_daily_loss_quote": float(request.core_config.risk_caps.max_daily_loss_quote),
                "max_drawdown_ratio": float(request.core_config.risk_caps.max_drawdown_ratio),
                "max_orders_per_window": int(request.core_config.risk_caps.max_orders_per_window),
                "order_window_bars": int(request.core_config.risk_caps.order_window_bars),
            },
            "kill_switch": {
                "mode": str(request.core_config.kill_switch.mode),
                "manual_trigger_event_seq": request.core_config.kill_switch.manual_trigger_event_seq,
            },
        },
        "models": {
            "fee": {"version": request.core_config.fee_model.version},
            "slippage": {"version": request.core_config.slippage_model.version},
            "funding": {"version": request.core_config.funding_model.version},
            "liquidation": {"version": request.core_config.liquidation_model.version},
        },
        "inputs": {
            "data_path": data_ref,
            "data_file_sha256": data_file_sha256,
            "expected_data_sha256": request.data_sha256,
            "bars_sha256": bars_sha256,
        },
        "deterministic_seeds": {"core_rng_seed": int(request.seed)},
        "replay_identity": {
            "tuple": replay_tuple,
            "digest_sha256": replay_digest,
        },
        "artifacts": list(artifacts),
    }


def _validate_manifest_schema(payload: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "numeric_policy_id",
        "numeric_policy",
        "run_id",
        "run_status",
        "symbol",
        "timeframe",
        "strategy",
        "risk",
        "models",
        "inputs",
        "deterministic_seeds",
        "replay_identity",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "manifest missing required fields",
            {"missing_fields": missing, "artifact": "paper_run_manifest.json"},
        )
    if payload.get("schema_version") != PAPER_RUN_MANIFEST_SCHEMA:
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "manifest schema_version invalid",
            {"artifact": "paper_run_manifest.json"},
        )
    if payload.get("numeric_policy_id") != NUMERIC_POLICY_ID:
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "manifest numeric_policy_id invalid",
            {"artifact": "paper_run_manifest.json"},
        )
    if payload.get("numeric_policy") != NUMERIC_POLICY:
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "manifest numeric_policy invalid",
            {"artifact": "paper_run_manifest.json"},
        )
    if payload.get("run_status") not in {RUN_STATUS_SUCCEEDED, RUN_STATUS_FAILED}:
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "manifest run_status invalid",
            {"artifact": "paper_run_manifest.json"},
        )
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not all(isinstance(item, str) for item in artifacts):
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "manifest artifacts invalid",
            {"artifact": "paper_run_manifest.json"},
        )


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise S2ArtifactError(
            "SCHEMA_INVALID", "artifact invalid json", {"artifact": path.name}
        ) from exc
    if not isinstance(payload, dict):
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "artifact root must be object",
            {"artifact": path.name},
        )
    return payload


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    text: str
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise S2ArtifactError(
            "SCHEMA_INVALID", "artifact not readable", {"artifact": path.name}
        ) from exc
    rows: list[dict[str, Any]] = []
    for idx, line in enumerate(text.splitlines()):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise S2ArtifactError(
                "SCHEMA_INVALID",
                "artifact jsonl line invalid",
                {"artifact": path.name, "line_index": idx},
            ) from exc
        if not isinstance(payload, dict):
            raise S2ArtifactError(
                "SCHEMA_INVALID",
                "artifact jsonl line must be object",
                {"artifact": path.name, "line_index": idx},
            )
        rows.append(payload)
    return rows


def _validate_jsonl_schema(path: Path, rows: list[dict[str, Any]]) -> None:
    required_fields = JSONL_REQUIRED_FIELDS[path.name]
    expected_schema = JSONL_SCHEMAS[path.name]
    for idx, row in enumerate(rows):
        missing = sorted(required_fields - set(row.keys()))
        if missing:
            raise S2ArtifactError(
                "SCHEMA_INVALID",
                "artifact jsonl row missing required fields",
                {"artifact": path.name, "line_index": idx, "missing_fields": missing},
            )
        if row.get("schema_version") != expected_schema:
            raise S2ArtifactError(
                "SCHEMA_INVALID",
                "artifact jsonl row schema_version invalid",
                {
                    "artifact": path.name,
                    "line_index": idx,
                    "expected": expected_schema,
                    "actual": row.get("schema_version"),
                },
            )
        if row.get("numeric_policy_id") != NUMERIC_POLICY_ID:
            raise S2ArtifactError(
                "SCHEMA_INVALID",
                "artifact jsonl row numeric_policy_id invalid",
                {
                    "artifact": path.name,
                    "line_index": idx,
                    "expected": NUMERIC_POLICY_ID,
                    "actual": row.get("numeric_policy_id"),
                },
            )


def _sorted_rows_for_artifact(name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return stable_sort_records(rows, key_fields=JSONL_SORT_KEYS[name])


def _iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for child in value.values():
            yield from _iter_strings(child)
        return
    if isinstance(value, list):
        for child in value:
            yield from _iter_strings(child)


def _assert_no_forbidden_paths(value: Any, *, artifact: str) -> None:
    for text in _iter_strings(value):
        if contains_forbidden_path_token(text):
            raise S2ArtifactError(
                "SCHEMA_INVALID",
                "artifact contains forbidden absolute or OS-specific path token",
                {"artifact": artifact, "value": text},
            )


def _assert_normalized_timestamps(value: Any, *, artifact: str) -> None:
    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                if key == "ts_utc":
                    if not isinstance(child, str):
                        raise S2ArtifactError(
                            "SCHEMA_INVALID",
                            "ts_utc must be a string",
                            {"artifact": artifact},
                        )
                    try:
                        canonical = canonicalize_timestamp_utc(child)
                    except ValueError as exc:
                        raise S2ArtifactError(
                            "SCHEMA_INVALID",
                            "ts_utc is not a valid UTC timestamp",
                            {"artifact": artifact, "value": child},
                        ) from exc
                    if canonical != child:
                        raise S2ArtifactError(
                            "SCHEMA_INVALID",
                            "ts_utc timestamp is not canonical UTC",
                            {"artifact": artifact, "value": child, "expected": canonical},
                        )
                _walk(child)
        elif isinstance(node, list):
            for child in node:
                _walk(child)

    _walk(value)


def _read_artifact_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise S2ArtifactError(
            "SCHEMA_INVALID", "artifact not readable", {"artifact": path.name}
        ) from exc


def _validate_artifact_encoding(root: Path, name: str) -> None:
    data = _read_artifact_bytes(root / name)
    validate_utf8_lf_bytes(data, artifact=name)


def _collect_file_entries(root: Path, files: Iterable[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for name in sorted(files):
        data = _read_artifact_bytes(root / name)
        validate_utf8_lf_bytes(data, artifact=name)
        entries.append(
            {
                "path": name,
                "size_bytes": len(data),
                "sha256": sha256_hex_bytes(data),
            }
        )
    return entries


def _pack_hash_scope_from_artifacts(artifacts: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        name for name in sorted(set(artifacts)) if name not in PACK_HASH_EXCLUDED_ARTIFACTS
    )


def _build_artifact_pack_manifest(
    run_id: str,
    root: Path,
    *,
    artifacts: tuple[str, ...],
    run_status: str,
) -> dict[str, Any]:
    hash_scope = _pack_hash_scope_from_artifacts(artifacts)
    file_entries = _collect_file_entries(root, hash_scope)
    return {
        "schema_version": ARTIFACT_PACK_MANIFEST_SCHEMA,
        "numeric_policy_id": NUMERIC_POLICY_ID,
        "numeric_policy": dict(NUMERIC_POLICY),
        "run_id": run_id,
        "run_status": run_status,
        "hash_scope": {
            "included_files": [row["path"] for row in file_entries],
            "excluded_files": sorted(PACK_HASH_EXCLUDED_ARTIFACTS),
        },
        "files": file_entries,
        "root_hash": build_pack_root_hash(file_entries),
    }


def _validate_ordering(path: Path, rows: list[dict[str, Any]]) -> None:
    expected = _sorted_rows_for_artifact(path.name, rows)
    for idx, (actual_row, expected_row) in enumerate(zip(rows, expected, strict=True)):
        if canonical_json_bytes(actual_row) != canonical_json_bytes(expected_row):
            raise S2ArtifactError(
                "ORDERING_INVALID",
                "artifact row ordering invalid",
                {"artifact": path.name, "line_index": idx},
            )


def _validate_artifact_pack_manifest(
    root: Path,
    payload: Mapping[str, Any],
    *,
    expected_hash_scope: tuple[str, ...],
    expected_run_status: str,
) -> dict[str, str]:
    if payload.get("schema_version") != ARTIFACT_PACK_MANIFEST_SCHEMA:
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "artifact pack manifest schema invalid",
            {"artifact": "artifact_pack_manifest.json"},
        )
    if payload.get("numeric_policy_id") != NUMERIC_POLICY_ID:
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "artifact pack numeric_policy_id mismatch",
            {
                "artifact": "artifact_pack_manifest.json",
                "expected": NUMERIC_POLICY_ID,
                "actual": payload.get("numeric_policy_id"),
            },
        )
    numeric_policy = payload.get("numeric_policy")
    if numeric_policy != NUMERIC_POLICY:
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "artifact pack numeric_policy mismatch",
            {"artifact": "artifact_pack_manifest.json"},
        )
    if payload.get("run_status") != expected_run_status:
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "artifact pack run_status mismatch",
            {"artifact": "artifact_pack_manifest.json"},
        )
    files = payload.get("files")
    if not isinstance(files, list):
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "artifact pack files invalid",
            {"artifact": "artifact_pack_manifest.json"},
        )
    root_hash = str(payload.get("root_hash") or "")
    if not _SHA256_RE.fullmatch(root_hash):
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "artifact pack root_hash invalid",
            {"artifact": "artifact_pack_manifest.json"},
        )

    parsed_entries: list[dict[str, Any]] = []
    for idx, row in enumerate(files):
        if not isinstance(row, dict):
            raise S2ArtifactError(
                "SCHEMA_INVALID",
                "artifact pack file entry invalid",
                {"artifact": "artifact_pack_manifest.json", "entry_index": idx},
            )
        path = str(row.get("path") or "")
        sha = str(row.get("sha256") or "")
        size_bytes = row.get("size_bytes")
        if path not in expected_hash_scope:
            raise S2ArtifactError(
                "SCHEMA_INVALID",
                "artifact pack includes unsupported file path",
                {"artifact": "artifact_pack_manifest.json", "path": path},
            )
        if contains_forbidden_path_token(path):
            raise S2ArtifactError(
                "SCHEMA_INVALID",
                "artifact pack includes forbidden path token",
                {"artifact": "artifact_pack_manifest.json", "path": path},
            )
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
            raise S2ArtifactError(
                "SCHEMA_INVALID",
                "artifact pack size_bytes invalid",
                {"artifact": "artifact_pack_manifest.json", "path": path},
            )
        if not _SHA256_RE.fullmatch(sha):
            raise S2ArtifactError(
                "SCHEMA_INVALID",
                "artifact pack sha256 invalid",
                {"artifact": "artifact_pack_manifest.json", "path": path},
            )
        parsed_entries.append({"path": path, "size_bytes": size_bytes, "sha256": sha})

    if [row["path"] for row in parsed_entries] != sorted(row["path"] for row in parsed_entries):
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "artifact pack file list is not sorted by path",
            {"artifact": "artifact_pack_manifest.json"},
        )

    manifest_paths = {row["path"] for row in parsed_entries}
    expected_paths = set(expected_hash_scope)
    if manifest_paths != expected_paths:
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "artifact pack file set mismatch",
            {
                "artifact": "artifact_pack_manifest.json",
                "missing": sorted(expected_paths - manifest_paths),
                "unexpected": sorted(manifest_paths - expected_paths),
            },
        )

    actual_entries = _collect_file_entries(root, expected_hash_scope)
    if parsed_entries != actual_entries:
        raise S2ArtifactError(
            "DIGEST_MISMATCH",
            "artifact pack file hashes mismatch",
            {"artifact": "artifact_pack_manifest.json"},
        )
    actual_root = build_pack_root_hash(actual_entries)
    if actual_root != root_hash:
        raise S2ArtifactError(
            "DIGEST_MISMATCH",
            "artifact pack root hash mismatch",
            {
                "artifact": "artifact_pack_manifest.json",
                "expected": root_hash,
                "actual": actual_root,
            },
        )
    return {row["path"]: row["sha256"] for row in actual_entries}


def _validate_run_digests(
    root: Path,
    payload: Mapping[str, Any],
    *,
    pack_file_hashes: Mapping[str, str],
    manifest_replay_digest: str,
    pack_root_hash: str,
    expected_artifacts: tuple[str, ...],
) -> dict[str, str]:
    if payload.get("schema_version") != RUN_DIGESTS_SCHEMA:
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "run_digests schema invalid",
            {"artifact": "run_digests.json"},
        )
    if payload.get("numeric_policy_id") != NUMERIC_POLICY_ID:
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "run_digests numeric_policy_id mismatch",
            {"artifact": "run_digests.json"},
        )
    if str(payload.get("numeric_policy_digest_sha256") or "") != NUMERIC_POLICY_DIGEST_SHA256:
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "run_digests numeric_policy_digest mismatch",
            {"artifact": "run_digests.json"},
        )

    digest_map = payload.get("artifact_sha256")
    if not isinstance(digest_map, dict):
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "run_digests artifact_sha256 invalid",
            {"artifact": "run_digests.json"},
        )

    expected_digest_keys = sorted(name for name in expected_artifacts if name != "run_digests.json")
    if sorted(digest_map.keys()) != expected_digest_keys:
        raise S2ArtifactError(
            "DIGEST_MISMATCH",
            "run_digests artifact_sha256 keys mismatch",
            {
                "artifact": "run_digests.json",
                "expected_keys": expected_digest_keys,
                "actual_keys": sorted(digest_map.keys()),
            },
        )

    for artifact_name in expected_digest_keys:
        actual_sha = sha256_hex_file(root / artifact_name)
        expected_sha = str(digest_map.get(artifact_name) or "")
        if actual_sha != expected_sha:
            raise S2ArtifactError(
                "DIGEST_MISMATCH",
                "artifact digest mismatch",
                {
                    "artifact": artifact_name,
                    "expected": expected_sha,
                    "actual": actual_sha,
                },
            )

    digested_pack_files = payload.get("artifact_pack_files_sha256")
    if not isinstance(digested_pack_files, dict):
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "run_digests artifact_pack_files_sha256 invalid",
            {"artifact": "run_digests.json"},
        )
    if dict(digested_pack_files) != dict(pack_file_hashes):
        raise S2ArtifactError(
            "DIGEST_MISMATCH",
            "run_digests artifact_pack_files_sha256 mismatch",
            {"artifact": "run_digests.json"},
        )

    digest_root_hash = str(payload.get("artifact_pack_root_hash") or "")
    if digest_root_hash != pack_root_hash:
        raise S2ArtifactError(
            "DIGEST_MISMATCH",
            "run_digests artifact_pack_root_hash mismatch",
            {
                "artifact": "run_digests.json",
                "expected": pack_root_hash,
                "actual": digest_root_hash,
            },
        )
    if not _SHA256_RE.fullmatch(digest_root_hash):
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "run_digests artifact_pack_root_hash invalid",
            {"artifact": "run_digests.json"},
        )

    replay_digest = str(payload.get("replay_identity_digest_sha256") or "")
    if replay_digest != manifest_replay_digest:
        raise S2ArtifactError(
            "DIGEST_MISMATCH",
            "replay identity digest mismatch",
            {"artifact": "run_digests.json"},
        )
    if not _SHA256_RE.fullmatch(replay_digest):
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "run_digests replay_identity_digest_sha256 invalid",
            {"artifact": "run_digests.json"},
        )

    result: dict[str, str] = {}
    for key, value in digest_map.items():
        result[str(key)] = str(value)
    return result


def _canonical_rows(rows: Iterable[Mapping[str, Any]], artifact_name: str) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        payload = dict(row)
        payload["numeric_policy_id"] = NUMERIC_POLICY_ID
        normalized.append(payload)
    return _sorted_rows_for_artifact(artifact_name, normalized)


def _replay_identity_tuple(
    *,
    bars_sha256: str,
    strategy_version: str,
    strategy_config_digest: str,
    risk_version: str,
    risk_config_digest: str,
    core_config: S2CoreConfig,
    seed: int,
) -> list[Any]:
    return [
        bars_sha256,
        strategy_version,
        strategy_config_digest,
        risk_version,
        risk_config_digest,
        core_config.fee_model.version,
        core_config.slippage_model.version,
        core_config.funding_model.version,
        core_config.liquidation_model.version,
        int(seed),
    ]


def _error_code_from_artifact_error(exc: S2ArtifactError) -> str:
    code = str(exc.code).strip().upper()
    if code == "INPUT_DIGEST_MISMATCH":
        return "DIGEST_MISMATCH"
    if code in ALLOWED_ERROR_CODES:
        return code
    return "SIMULATION_FAILED"


def _error_code_from_core_error(exc: S2CoreError) -> str:
    cause = exc.__cause__
    if isinstance(cause, FundingDataMissingError):
        return "MISSING_CRITICAL_FUNDING_WINDOW"
    if isinstance(cause, PositionInvariantError):
        return "DATA_INTEGRITY_FAILURE"
    text = str(exc)
    if "missing_critical_funding_window" in text:
        return "MISSING_CRITICAL_FUNDING_WINDOW"
    if "position invariant" in text or "position_" in text:
        return "DATA_INTEGRITY_FAILURE"
    return "SIMULATION_FAILED"


def _extract_missing_funding_ts(error: S2CoreError) -> str | None:
    cause = error.__cause__
    if isinstance(cause, FundingDataMissingError):
        return cause.ts_utc
    text = str(error)
    marker = "missing_critical_funding_window:"
    if marker in text:
        return text.split(marker, 1)[1].strip() or None
    return None


def _build_failure_context(
    *,
    code: str,
    exc: Exception,
    request: S2ArtifactRequest,
    bars: list[dict[str, Any]],
    data_file_sha256: str | None,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "run_id": request.run_id,
        "symbol": request.symbol,
        "timeframe": request.timeframe,
        "seed": int(request.seed),
        "data_path": canonicalize_artifact_path(request.data_path, repo_root=_repo_root()),
    }
    if data_file_sha256 is not None:
        context["data_file_sha256"] = data_file_sha256
    if isinstance(exc, S2ArtifactError):
        context.update(exc.details)
    if isinstance(exc, S2CoreError):
        context["core_error"] = str(exc)
        if code == "MISSING_CRITICAL_FUNDING_WINDOW":
            missing_ts = _extract_missing_funding_ts(exc)
            if missing_ts:
                ts_utc = canonicalize_timestamp_utc(missing_ts)
                context["missing_funding_ts_utc"] = ts_utc
                interval = max(int(request.core_config.funding_model.interval_minutes), 0)
                if interval > 0:
                    context["funding_interval_minutes"] = interval
                    context["funding_window_start_utc"] = ts_utc
                    context["funding_window_end_utc"] = ts_utc
    if bars:
        context["bar_count"] = len(bars)
        context["first_bar_ts_utc"] = bars[0]["ts_utc"]
        context["last_bar_ts_utc"] = bars[-1]["ts_utc"]
    return context


def _write_failure_artifact_pack(
    *,
    run_dir: Path,
    request: S2ArtifactRequest,
    failure_code: str,
    failure_message: str,
    failure_context: Mapping[str, Any],
    replay_tuple: list[Any],
    replay_digest: str,
    data_file_sha256: str | None,
    bars_sha256: str,
    strategy_config_digest: str,
    risk_config_digest: str,
    failure_ts_utc: str,
) -> None:
    for path in sorted(run_dir.iterdir()):
        if path.is_file():
            path.unlink()

    failure_artifacts = REQUIRED_FAILURE_ARTIFACTS
    manifest_payload = _manifest_payload(
        request,
        data_file_sha256=data_file_sha256 or "",
        bars_sha256=bars_sha256,
        strategy_config_digest=strategy_config_digest,
        risk_config_digest=risk_config_digest,
        replay_tuple=replay_tuple,
        replay_digest=replay_digest,
        artifacts=failure_artifacts,
        run_status=RUN_STATUS_FAILED,
    )
    write_canonical_json(run_dir / "paper_run_manifest.json", manifest_payload)

    risk_rows = _canonical_rows(
        [
            {
                "schema_version": RISK_EVENT_SCHEMA,
                "event_seq": -1,
                "ts_utc": failure_ts_utc,
                "reason_code": (
                    "digest_mismatch"
                    if failure_code in {"DIGEST_MISMATCH", "INPUT_DIGEST_MISMATCH"}
                    else failure_code.lower()
                ),
                "detail": failure_message,
            }
        ],
        "risk_events.jsonl",
    )
    write_canonical_jsonl(run_dir / "risk_events.jsonl", risk_rows)

    failure = S2StructuredFailure(
        error_code=failure_code,
        message=failure_message,
        context=dict(failure_context),
        source_component="s2.artifacts",
        source_stage="s2",
        source_function="run_s2_artifact_pack",
        timestamp=failure_ts_utc,
    )
    run_failure_payload = build_run_failure_payload(
        run_id=request.run_id,
        failure=failure,
        details={
            "numeric_policy_digest_sha256": NUMERIC_POLICY_DIGEST_SHA256,
        },
    )
    write_canonical_json(run_dir / "run_failure.json", run_failure_payload)

    pack_manifest = _build_artifact_pack_manifest(
        request.run_id,
        run_dir,
        artifacts=failure_artifacts,
        run_status=RUN_STATUS_FAILED,
    )
    write_canonical_json(run_dir / "artifact_pack_manifest.json", pack_manifest)

    artifact_digests = {
        name: sha256_hex_file(run_dir / name)
        for name in sorted(failure_artifacts)
        if name != "run_digests.json"
    }
    run_digests_payload = {
        "schema_version": RUN_DIGESTS_SCHEMA,
        "numeric_policy_id": NUMERIC_POLICY_ID,
        "numeric_policy_digest_sha256": NUMERIC_POLICY_DIGEST_SHA256,
        "run_id": request.run_id,
        "artifact_sha256": artifact_digests,
        "artifact_pack_root_hash": pack_manifest["root_hash"],
        "artifact_pack_files_sha256": {
            str(row["path"]): str(row["sha256"]) for row in pack_manifest["files"]
        },
        "replay_identity_digest_sha256": replay_digest,
    }
    write_canonical_json(run_dir / "run_digests.json", run_digests_payload)


def run_s2_artifact_pack(request: S2ArtifactRequest, output_root: Path) -> Path:
    run_id = _normalize_run_id(request.run_id)
    symbol = _require_nonempty(request.symbol, "symbol")
    timeframe = _require_nonempty(request.timeframe, "timeframe")
    strategy_version = _require_nonempty(request.strategy_version, "strategy_version")
    risk_version = _require_nonempty(request.risk_version, "risk_version")
    data_path = Path(_require_nonempty(request.data_path, "data_path")).resolve()
    run_dir = (output_root / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    strategy_config = dict(request.strategy_config)
    risk_config = dict(request.risk_config)
    strategy_config_digest = sha256_hex_bytes(canonical_json_bytes(strategy_config))
    risk_config_digest = sha256_hex_bytes(canonical_json_bytes(risk_config))
    bars: list[dict[str, Any]] = []
    data_file_sha256: str | None = None
    bars_sha256 = sha256_hex_bytes(canonical_json_bytes(_bars_payload(bars)))
    replay_tuple = _replay_identity_tuple(
        bars_sha256=bars_sha256,
        strategy_version=strategy_version,
        strategy_config_digest=strategy_config_digest,
        risk_version=risk_version,
        risk_config_digest=risk_config_digest,
        core_config=request.core_config,
        seed=int(request.seed),
    )
    replay_digest = sha256_hex_bytes(canonical_json_bytes(replay_tuple))

    def _failure_timestamp(core_error: S2CoreError | None = None) -> str:
        candidates = [row["ts_utc"] for row in bars]
        if core_error is not None:
            missing_ts = _extract_missing_funding_ts(core_error)
            if missing_ts:
                candidates.append(missing_ts)
        return deterministic_failure_timestamp(candidates)

    try:
        bars = _load_bars_from_csv(data_path)
        bars_sha256 = sha256_hex_bytes(canonical_json_bytes(_bars_payload(bars)))
        data_file_sha256 = sha256_hex_file(data_path)
        if request.data_sha256 is not None:
            expected_data_sha = str(request.data_sha256).strip()
            if expected_data_sha != data_file_sha256:
                raise S2ArtifactError(
                    "INPUT_DIGEST_MISMATCH",
                    "data_path sha256 mismatch",
                    {
                        "field": "data_sha256",
                        "expected": expected_data_sha,
                        "actual": data_file_sha256,
                    },
                )
        replay_tuple = _replay_identity_tuple(
            bars_sha256=bars_sha256,
            strategy_version=strategy_version,
            strategy_config_digest=strategy_config_digest,
            risk_version=risk_version,
            risk_config_digest=risk_config_digest,
            core_config=request.core_config,
            seed=int(request.seed),
        )
        replay_digest = sha256_hex_bytes(canonical_json_bytes(replay_tuple))

        core_config = S2CoreConfig(
            symbol=symbol,
            timeframe=timeframe,
            seed=int(request.seed),
            initial_cash_quote=float(request.core_config.initial_cash_quote),
            target_position_qty=float(request.core_config.target_position_qty),
            fee_model=request.core_config.fee_model,
            slippage_model=request.core_config.slippage_model,
            funding_model=request.core_config.funding_model,
            liquidation_model=request.core_config.liquidation_model,
            risk_caps=request.core_config.risk_caps,
            kill_switch=request.core_config.kill_switch,
        )

        result = run_s2_core_loop(
            bars=bars,
            config=core_config,
            strategy_fn=_strategy_fn_from_config(strategy_config),
            risk_fn=_risk_fn_from_config(risk_config),
        )
        manifest_payload = _manifest_payload(
            request,
            data_file_sha256=data_file_sha256,
            bars_sha256=bars_sha256,
            strategy_config_digest=strategy_config_digest,
            risk_config_digest=risk_config_digest,
            replay_tuple=replay_tuple,
            replay_digest=replay_digest,
            artifacts=REQUIRED_ARTIFACTS,
            run_status=RUN_STATUS_SUCCEEDED,
        )
        _validate_manifest_schema(manifest_payload)

        write_canonical_json(run_dir / "paper_run_manifest.json", manifest_payload)
        write_canonical_jsonl(
            run_dir / "decision_records.jsonl",
            _canonical_rows(result.decision_records, "decision_records.jsonl"),
        )
        write_canonical_jsonl(
            run_dir / "simulated_orders.jsonl",
            _canonical_rows(result.simulated_orders, "simulated_orders.jsonl"),
        )
        write_canonical_jsonl(
            run_dir / "simulated_fills.jsonl",
            _canonical_rows(result.simulated_fills, "simulated_fills.jsonl"),
        )
        write_canonical_jsonl(
            run_dir / "position_timeline.jsonl",
            _canonical_rows(result.position_timeline, "position_timeline.jsonl"),
        )
        write_canonical_jsonl(
            run_dir / "risk_events.jsonl",
            _canonical_rows(result.risk_events, "risk_events.jsonl"),
        )
        write_canonical_jsonl(
            run_dir / "funding_transfers.jsonl",
            _canonical_rows(result.funding_transfers, "funding_transfers.jsonl"),
        )
        write_canonical_json(
            run_dir / "cost_breakdown.json",
            {
                "schema_version": COST_BREAKDOWN_SCHEMA,
                "numeric_policy_id": NUMERIC_POLICY_ID,
                **result.cost_breakdown,
            },
        )

        artifact_pack_manifest = _build_artifact_pack_manifest(
            run_id,
            run_dir,
            artifacts=REQUIRED_ARTIFACTS,
            run_status=RUN_STATUS_SUCCEEDED,
        )
        write_canonical_json(run_dir / "artifact_pack_manifest.json", artifact_pack_manifest)

        artifact_digests = {
            name: sha256_hex_file(run_dir / name)
            for name in sorted(REQUIRED_ARTIFACTS)
            if name != "run_digests.json"
        }
        pack_file_hashes = {
            str(row["path"]): str(row["sha256"]) for row in artifact_pack_manifest["files"]
        }
        run_digests_payload = {
            "schema_version": RUN_DIGESTS_SCHEMA,
            "numeric_policy_id": NUMERIC_POLICY_ID,
            "numeric_policy_digest_sha256": NUMERIC_POLICY_DIGEST_SHA256,
            "run_id": run_id,
            "artifact_sha256": artifact_digests,
            "artifact_pack_root_hash": artifact_pack_manifest["root_hash"],
            "artifact_pack_files_sha256": pack_file_hashes,
            "replay_identity_digest_sha256": replay_digest,
        }
        write_canonical_json(run_dir / "run_digests.json", run_digests_payload)

        validate_s2_artifact_pack(run_dir)
        return run_dir
    except S2CoreError as exc:
        failure_code = _error_code_from_core_error(exc)
        failure_context = _build_failure_context(
            code=failure_code,
            exc=exc,
            request=request,
            bars=bars,
            data_file_sha256=data_file_sha256,
        )
        _write_failure_artifact_pack(
            run_dir=run_dir,
            request=S2ArtifactRequest(
                run_id=run_id,
                symbol=symbol,
                timeframe=timeframe,
                seed=int(request.seed),
                data_path=request.data_path,
                data_sha256=request.data_sha256,
                strategy_version=strategy_version,
                strategy_config=strategy_config,
                risk_version=risk_version,
                risk_config=risk_config,
                core_config=request.core_config,
            ),
            failure_code=failure_code,
            failure_message=str(exc),
            failure_context=failure_context,
            replay_tuple=replay_tuple,
            replay_digest=replay_digest,
            data_file_sha256=data_file_sha256,
            bars_sha256=bars_sha256,
            strategy_config_digest=strategy_config_digest,
            risk_config_digest=risk_config_digest,
            failure_ts_utc=_failure_timestamp(exc),
        )
        raise S2ArtifactError(failure_code, "core loop failed", {"error": str(exc)}) from exc
    except S2ArtifactError as exc:
        failure_code = _error_code_from_artifact_error(exc)
        failure_context = _build_failure_context(
            code=failure_code,
            exc=exc,
            request=request,
            bars=bars,
            data_file_sha256=data_file_sha256,
        )
        _write_failure_artifact_pack(
            run_dir=run_dir,
            request=S2ArtifactRequest(
                run_id=run_id,
                symbol=symbol,
                timeframe=timeframe,
                seed=int(request.seed),
                data_path=request.data_path,
                data_sha256=request.data_sha256,
                strategy_version=strategy_version,
                strategy_config=strategy_config,
                risk_version=risk_version,
                risk_config=risk_config,
                core_config=request.core_config,
            ),
            failure_code=failure_code,
            failure_message=str(exc),
            failure_context=failure_context,
            replay_tuple=replay_tuple,
            replay_digest=replay_digest,
            data_file_sha256=data_file_sha256,
            bars_sha256=bars_sha256,
            strategy_config_digest=strategy_config_digest,
            risk_config_digest=risk_config_digest,
            failure_ts_utc=_failure_timestamp(),
        )
        raise


def _expected_artifacts_for_run_status(run_status: str) -> tuple[str, ...]:
    if run_status == RUN_STATUS_SUCCEEDED:
        return REQUIRED_ARTIFACTS
    if run_status == RUN_STATUS_FAILED:
        return REQUIRED_FAILURE_ARTIFACTS
    raise S2ArtifactError(
        "SCHEMA_INVALID",
        "manifest run_status invalid",
        {"artifact": "paper_run_manifest.json"},
    )


def _validate_run_failure_payload(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != RUN_FAILURE_SCHEMA:
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "run_failure schema invalid",
            {"artifact": "run_failure.json"},
        )
    if payload.get("numeric_policy_id") != NUMERIC_POLICY_ID:
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "run_failure numeric_policy_id invalid",
            {"artifact": "run_failure.json"},
        )
    error = payload.get("error")
    if not isinstance(error, dict):
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "run_failure error payload invalid",
            {"artifact": "run_failure.json"},
        )
    if error.get("schema_version") != "s2/error/v1":
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "run_failure error schema invalid",
            {"artifact": "run_failure.json"},
        )
    if error.get("numeric_policy_id") != NUMERIC_POLICY_ID:
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "run_failure error numeric policy mismatch",
            {"artifact": "run_failure.json"},
        )
    code = str(error.get("error_code") or "")
    if code not in ALLOWED_ERROR_CODES:
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "run_failure error_code invalid",
            {"artifact": "run_failure.json", "error_code": code},
        )
    if error.get("severity") != "FATAL":
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "run_failure severity invalid",
            {"artifact": "run_failure.json"},
        )
    source = error.get("source")
    if not isinstance(source, dict):
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "run_failure source invalid",
            {"artifact": "run_failure.json"},
        )
    required_source_fields = {"component", "stage", "function"}
    missing_source = sorted(required_source_fields - set(source.keys()))
    if missing_source:
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "run_failure source missing required fields",
            {"artifact": "run_failure.json", "missing_fields": missing_source},
        )
    timestamp = error.get("timestamp")
    if not isinstance(timestamp, str):
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "run_failure timestamp invalid",
            {"artifact": "run_failure.json"},
        )
    if canonicalize_timestamp_utc(timestamp) != timestamp:
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "run_failure timestamp not canonical",
            {"artifact": "run_failure.json"},
        )


def validate_s2_artifact_pack(run_dir: Path) -> dict[str, Any]:
    root = run_dir.resolve()
    if not root.exists() or not root.is_dir():
        raise S2ArtifactError("ARTIFACT_MISSING", "run directory missing", {"run_dir": str(root)})

    manifest_path = root / "paper_run_manifest.json"
    if not manifest_path.exists() or not manifest_path.is_file():
        raise S2ArtifactError(
            "ARTIFACT_MISSING", "required artifact missing", {"artifact": "paper_run_manifest.json"}
        )
    _validate_artifact_encoding(root, "paper_run_manifest.json")

    manifest = _load_json(manifest_path)
    _validate_manifest_schema(manifest)
    _assert_no_forbidden_paths(manifest, artifact="paper_run_manifest.json")
    _assert_normalized_timestamps(manifest, artifact="paper_run_manifest.json")
    run_status = str(manifest["run_status"])
    expected_artifacts = _expected_artifacts_for_run_status(run_status)

    declared_artifacts = tuple(str(item) for item in manifest["artifacts"])
    if declared_artifacts != expected_artifacts:
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "manifest artifact list mismatch for run_status",
            {
                "artifact": "paper_run_manifest.json",
                "run_status": run_status,
                "expected": list(expected_artifacts),
                "actual": list(declared_artifacts),
            },
        )

    for name in expected_artifacts:
        artifact = root / name
        if not artifact.exists():
            raise S2ArtifactError(
                "ARTIFACT_MISSING", "required artifact missing", {"artifact": name}
            )
        if not artifact.is_file():
            raise S2ArtifactError(
                "ARTIFACT_MISSING", "required artifact invalid", {"artifact": name}
            )
        _validate_artifact_encoding(root, name)

    if run_status == RUN_STATUS_SUCCEEDED:
        if (root / "run_failure.json").exists():
            raise S2ArtifactError(
                "SCHEMA_INVALID",
                "run_failure must not exist for succeeded runs",
                {"artifact": "run_failure.json"},
            )
        for jsonl_name in JSONL_ARTIFACTS:
            path = root / jsonl_name
            rows = _load_jsonl(path)
            _validate_jsonl_schema(path, rows)
            _validate_ordering(path, rows)
            _assert_no_forbidden_paths(rows, artifact=jsonl_name)
            _assert_normalized_timestamps(rows, artifact=jsonl_name)

        costs = _load_json(root / "cost_breakdown.json")
        if costs.get("schema_version") != COST_BREAKDOWN_SCHEMA:
            raise S2ArtifactError(
                "SCHEMA_INVALID",
                "cost_breakdown schema invalid",
                {"artifact": "cost_breakdown.json"},
            )
        if costs.get("numeric_policy_id") != NUMERIC_POLICY_ID:
            raise S2ArtifactError(
                "SCHEMA_INVALID",
                "cost_breakdown numeric_policy_id mismatch",
                {"artifact": "cost_breakdown.json"},
            )
        required_cost_fields = {
            "schema_version",
            "numeric_policy_id",
            "fees_quote",
            "slippage_quote",
            "funding_quote",
            "total_cost_quote",
        }
        missing_cost_fields = sorted(required_cost_fields - set(costs.keys()))
        if missing_cost_fields:
            raise S2ArtifactError(
                "SCHEMA_INVALID",
                "cost_breakdown missing required fields",
                {"missing_fields": missing_cost_fields, "artifact": "cost_breakdown.json"},
            )
        _assert_no_forbidden_paths(costs, artifact="cost_breakdown.json")
        _assert_normalized_timestamps(costs, artifact="cost_breakdown.json")
    else:
        for name in REQUIRED_ARTIFACTS:
            if name in REQUIRED_FAILURE_ARTIFACTS:
                continue
            if (root / name).exists():
                raise S2ArtifactError(
                    "SCHEMA_INVALID",
                    "succeeded-only artifact present in failed run",
                    {"artifact": name},
                )
        risk_rows = _load_jsonl(root / "risk_events.jsonl")
        _validate_jsonl_schema(root / "risk_events.jsonl", risk_rows)
        _validate_ordering(root / "risk_events.jsonl", risk_rows)
        _assert_no_forbidden_paths(risk_rows, artifact="risk_events.jsonl")
        _assert_normalized_timestamps(risk_rows, artifact="risk_events.jsonl")
        run_failure = _load_json(root / "run_failure.json")
        _validate_run_failure_payload(run_failure)
        _assert_no_forbidden_paths(run_failure, artifact="run_failure.json")
        _assert_normalized_timestamps(run_failure, artifact="run_failure.json")

    pack_manifest = _load_json(root / "artifact_pack_manifest.json")
    _assert_no_forbidden_paths(pack_manifest, artifact="artifact_pack_manifest.json")
    _assert_normalized_timestamps(pack_manifest, artifact="artifact_pack_manifest.json")
    pack_file_hashes = _validate_artifact_pack_manifest(
        root,
        pack_manifest,
        expected_hash_scope=_pack_hash_scope_from_artifacts(expected_artifacts),
        expected_run_status=run_status,
    )
    pack_root_hash = str(pack_manifest["root_hash"])

    run_digests = _load_json(root / "run_digests.json")
    _assert_no_forbidden_paths(run_digests, artifact="run_digests.json")
    _assert_normalized_timestamps(run_digests, artifact="run_digests.json")
    replay_identity = manifest.get("replay_identity")
    if not isinstance(replay_identity, dict):
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "manifest replay_identity invalid",
            {"artifact": "paper_run_manifest.json"},
        )
    replay_digest = str(replay_identity.get("digest_sha256") or "")
    digest_map = _validate_run_digests(
        root,
        run_digests,
        pack_file_hashes=pack_file_hashes,
        manifest_replay_digest=replay_digest,
        pack_root_hash=pack_root_hash,
        expected_artifacts=expected_artifacts,
    )

    return {
        "run_dir": str(root),
        "run_id": manifest["run_id"],
        "run_status": run_status,
        "artifact_sha256": digest_map,
        "artifact_pack_root_hash": pack_root_hash,
        "artifact_pack_file_sha256": dict(pack_file_hashes),
        "replay_identity_digest_sha256": replay_digest,
    }
