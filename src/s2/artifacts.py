from __future__ import annotations

import csv
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from .canonical import (
    build_pack_root_hash,
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


PAPER_RUN_MANIFEST_SCHEMA = "s2/paper_run_manifest/v1"
COST_BREAKDOWN_SCHEMA = "s2/cost_breakdown/v1"
ARTIFACT_PACK_MANIFEST_SCHEMA = "s2/artifact_pack_manifest/v1"
RUN_DIGESTS_SCHEMA = "s2/run_digests/v1"

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

PACK_HASH_EXCLUDED_ARTIFACTS = frozenset({"artifact_pack_manifest.json", "run_digests.json"})
PACK_HASH_SCOPE_ARTIFACTS = tuple(
    name for name in REQUIRED_ARTIFACTS if name not in PACK_HASH_EXCLUDED_ARTIFACTS
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
        "event_seq",
        "ts_utc",
        "decision",
        "decision_time",
        "seed",
    },
    "simulated_orders.jsonl": {
        "schema_version",
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
        "event_seq",
        "ts_utc",
        "reason_code",
        "detail",
    },
    "funding_transfers.jsonl": {
        "schema_version",
        "event_seq",
        "ts_utc",
        "funding_rate",
        "position_qty",
        "mark_price",
        "transfer_quote",
    },
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
                "INPUT_INVALID",
                "data row invalid",
                {"field": "data_path", "row_index": idx},
            ) from exc
    return bars


def _write_kill_switch_event(run_dir: Path, reason_code: str, detail: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    write_canonical_jsonl(
        run_dir / "risk_events.jsonl",
        [
            {
                "schema_version": RISK_EVENT_SCHEMA,
                "event_seq": -1,
                "ts_utc": "1970-01-01T00:00:00Z",
                "reason_code": reason_code,
                "detail": detail,
            }
        ],
    )


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
) -> dict[str, Any]:
    data_ref = canonicalize_artifact_path(request.data_path, repo_root=_repo_root())
    return {
        "schema_version": PAPER_RUN_MANIFEST_SCHEMA,
        "run_id": request.run_id,
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
        "artifacts": list(REQUIRED_ARTIFACTS),
    }


def _validate_manifest_schema(payload: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "run_id",
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


def _build_artifact_pack_manifest(run_id: str, root: Path) -> dict[str, Any]:
    file_entries = _collect_file_entries(root, PACK_HASH_SCOPE_ARTIFACTS)
    return {
        "schema_version": ARTIFACT_PACK_MANIFEST_SCHEMA,
        "run_id": run_id,
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


def _validate_artifact_pack_manifest(root: Path, payload: Mapping[str, Any]) -> dict[str, str]:
    if payload.get("schema_version") != ARTIFACT_PACK_MANIFEST_SCHEMA:
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "artifact pack manifest schema invalid",
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
        if path not in PACK_HASH_SCOPE_ARTIFACTS:
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
    expected_paths = set(PACK_HASH_SCOPE_ARTIFACTS)
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

    actual_entries = _collect_file_entries(root, PACK_HASH_SCOPE_ARTIFACTS)
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
) -> dict[str, str]:
    if payload.get("schema_version") != RUN_DIGESTS_SCHEMA:
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "run_digests schema invalid",
            {"artifact": "run_digests.json"},
        )

    digest_map = payload.get("artifact_sha256")
    if not isinstance(digest_map, dict):
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "run_digests artifact_sha256 invalid",
            {"artifact": "run_digests.json"},
        )

    expected_digest_keys = sorted(name for name in REQUIRED_ARTIFACTS if name != "run_digests.json")
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
    normalized = [dict(row) for row in rows]
    return _sorted_rows_for_artifact(artifact_name, normalized)


def run_s2_artifact_pack(request: S2ArtifactRequest, output_root: Path) -> Path:
    run_id = _normalize_run_id(request.run_id)
    symbol = _require_nonempty(request.symbol, "symbol")
    timeframe = _require_nonempty(request.timeframe, "timeframe")
    strategy_version = _require_nonempty(request.strategy_version, "strategy_version")
    risk_version = _require_nonempty(request.risk_version, "risk_version")
    data_path = Path(_require_nonempty(request.data_path, "data_path")).resolve()
    run_dir = (output_root / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    bars = _load_bars_from_csv(data_path)

    strategy_config = dict(request.strategy_config)
    risk_config = dict(request.risk_config)

    data_file_sha256 = sha256_hex_file(data_path)
    if request.data_sha256 is not None:
        expected_data_sha = str(request.data_sha256).strip()
        if expected_data_sha != data_file_sha256:
            _write_kill_switch_event(
                run_dir,
                "digest_mismatch",
                "input data digest mismatch",
            )
            raise S2ArtifactError(
                "INPUT_DIGEST_MISMATCH",
                "data_path sha256 mismatch",
                {
                    "field": "data_sha256",
                    "expected": expected_data_sha,
                    "actual": data_file_sha256,
                },
            )
    bars_sha256 = sha256_hex_bytes(canonical_json_bytes(_bars_payload(bars)))
    strategy_config_digest = sha256_hex_bytes(canonical_json_bytes(strategy_config))
    risk_config_digest = sha256_hex_bytes(canonical_json_bytes(risk_config))

    replay_tuple = [
        bars_sha256,
        strategy_version,
        strategy_config_digest,
        risk_version,
        risk_config_digest,
        request.core_config.fee_model.version,
        request.core_config.slippage_model.version,
        request.core_config.funding_model.version,
        request.core_config.liquidation_model.version,
        int(request.seed),
    ]
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

    try:
        result = run_s2_core_loop(
            bars=bars,
            config=core_config,
            strategy_fn=_strategy_fn_from_config(strategy_config),
            risk_fn=_risk_fn_from_config(risk_config),
        )
    except S2CoreError as exc:
        _write_kill_switch_event(
            run_dir,
            "data_integrity_failure",
            str(exc),
        )
        raise S2ArtifactError("SIMULATION_FAILED", "core loop failed", {"error": str(exc)}) from exc

    manifest_payload = _manifest_payload(
        S2ArtifactRequest(
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
            core_config=core_config,
        ),
        data_file_sha256=data_file_sha256,
        bars_sha256=bars_sha256,
        strategy_config_digest=strategy_config_digest,
        risk_config_digest=risk_config_digest,
        replay_tuple=replay_tuple,
        replay_digest=replay_digest,
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
        {"schema_version": COST_BREAKDOWN_SCHEMA, **result.cost_breakdown},
    )

    artifact_pack_manifest = _build_artifact_pack_manifest(run_id, run_dir)
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
        "run_id": run_id,
        "artifact_sha256": artifact_digests,
        "artifact_pack_root_hash": artifact_pack_manifest["root_hash"],
        "artifact_pack_files_sha256": pack_file_hashes,
        "replay_identity_digest_sha256": replay_digest,
    }
    write_canonical_json(run_dir / "run_digests.json", run_digests_payload)

    validate_s2_artifact_pack(run_dir)
    return run_dir


def validate_s2_artifact_pack(run_dir: Path) -> dict[str, Any]:
    root = run_dir.resolve()
    if not root.exists() or not root.is_dir():
        raise S2ArtifactError("ARTIFACT_MISSING", "run directory missing", {"run_dir": str(root)})

    for name in REQUIRED_ARTIFACTS:
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

    manifest = _load_json(root / "paper_run_manifest.json")
    _validate_manifest_schema(manifest)
    _assert_no_forbidden_paths(manifest, artifact="paper_run_manifest.json")
    _assert_normalized_timestamps(manifest, artifact="paper_run_manifest.json")

    for jsonl_name in JSONL_SCHEMAS:
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
    required_cost_fields = {
        "schema_version",
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

    pack_manifest = _load_json(root / "artifact_pack_manifest.json")
    _assert_no_forbidden_paths(pack_manifest, artifact="artifact_pack_manifest.json")
    _assert_normalized_timestamps(pack_manifest, artifact="artifact_pack_manifest.json")
    pack_file_hashes = _validate_artifact_pack_manifest(root, pack_manifest)
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
    )

    return {
        "run_dir": str(root),
        "run_id": manifest["run_id"],
        "artifact_sha256": digest_map,
        "artifact_pack_root_hash": pack_root_hash,
        "artifact_pack_file_sha256": dict(pack_file_hashes),
        "replay_identity_digest_sha256": replay_digest,
    }
