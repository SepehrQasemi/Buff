from __future__ import annotations

from dataclasses import dataclass, field
import csv
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from .canonical import (
    canonical_json_bytes,
    sha256_hex_bytes,
    sha256_hex_file,
    write_canonical_json,
    write_canonical_jsonl,
)
from .core import Bar, S2CoreConfig, S2CoreError, run_s2_core_loop


REQUIRED_ARTIFACTS = (
    "paper_run_manifest.json",
    "decision_records.jsonl",
    "simulated_orders.jsonl",
    "simulated_fills.jsonl",
    "position_timeline.jsonl",
    "risk_events.jsonl",
    "funding_transfers.jsonl",
    "cost_breakdown.json",
    "run_digests.json",
)

_RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")


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


def _require_nonempty(value: str, field: str) -> str:
    text = str(value).strip()
    if not text:
        raise S2ArtifactError("INPUT_MISSING", f"{field} is required", {"field": field})
    return text


def _load_bars_from_csv(path: Path) -> list[Bar]:
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

    bars: list[Bar] = []
    for idx, row in enumerate(rows):
        try:
            ts = str(row.get("timestamp") or row.get("ts_utc") or "").strip()
            if not ts:
                raise ValueError("missing timestamp")
            bars.append(
                Bar(
                    ts_utc=ts,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0.0),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise S2ArtifactError(
                "INPUT_INVALID",
                "data row invalid",
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


def _bars_payload(bars: Iterable[Bar]) -> list[dict[str, Any]]:
    return [
        {
            "ts_utc": row.ts_utc,
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
            "volume": float(row.volume),
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
    return {
        "schema_version": "s2.paper_run_manifest.v1",
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
        },
        "models": {
            "fee": {"version": request.core_config.fee_model.version},
            "slippage": {"version": request.core_config.slippage_model.version},
            "funding": {"version": request.core_config.funding_model.version},
            "liquidation": {"version": request.core_config.liquidation_model.version},
        },
        "inputs": {
            "data_path": request.data_path,
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
    if payload.get("schema_version") != "s2.paper_run_manifest.v1":
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
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise S2ArtifactError(
            "SCHEMA_INVALID", "artifact not readable", {"artifact": path.name}
        ) from exc
    rows: list[dict[str, Any]] = []
    for idx, line in enumerate(lines):
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


def _validate_jsonl_schema(path: Path, required_fields: set[str]) -> None:
    rows = _load_jsonl(path)
    for idx, row in enumerate(rows):
        missing = sorted(required_fields - set(row.keys()))
        if missing:
            raise S2ArtifactError(
                "SCHEMA_INVALID",
                "artifact jsonl row missing required fields",
                {"artifact": path.name, "line_index": idx, "missing_fields": missing},
            )


def run_s2_artifact_pack(request: S2ArtifactRequest, output_root: Path) -> Path:
    run_id = _normalize_run_id(request.run_id)
    symbol = _require_nonempty(request.symbol, "symbol")
    timeframe = _require_nonempty(request.timeframe, "timeframe")
    strategy_version = _require_nonempty(request.strategy_version, "strategy_version")
    risk_version = _require_nonempty(request.risk_version, "risk_version")
    data_path = Path(_require_nonempty(request.data_path, "data_path")).resolve()
    bars = _load_bars_from_csv(data_path)

    strategy_config = dict(request.strategy_config)
    risk_config = dict(request.risk_config)

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

    run_dir = (output_root / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

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
    )

    try:
        result = run_s2_core_loop(
            bars=bars,
            config=core_config,
            strategy_fn=_strategy_fn_from_config(strategy_config),
            risk_fn=_risk_fn_from_config(risk_config),
        )
    except S2CoreError as exc:
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
    write_canonical_jsonl(run_dir / "decision_records.jsonl", result.decision_records)
    write_canonical_jsonl(run_dir / "simulated_orders.jsonl", result.simulated_orders)
    write_canonical_jsonl(run_dir / "simulated_fills.jsonl", result.simulated_fills)
    write_canonical_jsonl(run_dir / "position_timeline.jsonl", result.position_timeline)
    write_canonical_jsonl(run_dir / "risk_events.jsonl", result.risk_events)
    write_canonical_jsonl(run_dir / "funding_transfers.jsonl", result.funding_transfers)
    write_canonical_json(run_dir / "cost_breakdown.json", result.cost_breakdown)

    artifact_digests = {
        "paper_run_manifest.json": sha256_hex_file(run_dir / "paper_run_manifest.json"),
        "decision_records.jsonl": sha256_hex_file(run_dir / "decision_records.jsonl"),
        "simulated_orders.jsonl": sha256_hex_file(run_dir / "simulated_orders.jsonl"),
        "simulated_fills.jsonl": sha256_hex_file(run_dir / "simulated_fills.jsonl"),
        "position_timeline.jsonl": sha256_hex_file(run_dir / "position_timeline.jsonl"),
        "risk_events.jsonl": sha256_hex_file(run_dir / "risk_events.jsonl"),
        "funding_transfers.jsonl": sha256_hex_file(run_dir / "funding_transfers.jsonl"),
        "cost_breakdown.json": sha256_hex_file(run_dir / "cost_breakdown.json"),
    }
    run_digests_payload = {
        "schema_version": "s2.run_digests.v1",
        "run_id": run_id,
        "artifact_sha256": artifact_digests,
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

    manifest = _load_json(root / "paper_run_manifest.json")
    _validate_manifest_schema(manifest)

    _validate_jsonl_schema(
        root / "decision_records.jsonl",
        {"event_seq", "ts_utc", "decision", "decision_time", "seed"},
    )
    _validate_jsonl_schema(
        root / "simulated_orders.jsonl",
        {"order_id", "event_seq", "ts_utc", "symbol", "side", "qty", "order_type"},
    )
    _validate_jsonl_schema(
        root / "simulated_fills.jsonl",
        {
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
    )
    _validate_jsonl_schema(
        root / "position_timeline.jsonl",
        {
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
    )
    _validate_jsonl_schema(
        root / "risk_events.jsonl", {"event_seq", "ts_utc", "reason_code", "detail"}
    )
    _validate_jsonl_schema(
        root / "funding_transfers.jsonl",
        {"event_seq", "ts_utc", "funding_rate", "position_qty", "mark_price", "transfer_quote"},
    )

    costs = _load_json(root / "cost_breakdown.json")
    required_cost_fields = {"fees_quote", "slippage_quote", "funding_quote", "total_cost_quote"}
    missing_cost_fields = sorted(required_cost_fields - set(costs.keys()))
    if missing_cost_fields:
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "cost_breakdown missing required fields",
            {"missing_fields": missing_cost_fields, "artifact": "cost_breakdown.json"},
        )

    run_digests = _load_json(root / "run_digests.json")
    if run_digests.get("schema_version") != "s2.run_digests.v1":
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "run_digests schema invalid",
            {"artifact": "run_digests.json"},
        )
    digest_map = run_digests.get("artifact_sha256")
    if not isinstance(digest_map, dict):
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "run_digests artifact_sha256 invalid",
            {"artifact": "run_digests.json"},
        )

    expected = {
        "paper_run_manifest.json",
        "decision_records.jsonl",
        "simulated_orders.jsonl",
        "simulated_fills.jsonl",
        "position_timeline.jsonl",
        "risk_events.jsonl",
        "funding_transfers.jsonl",
        "cost_breakdown.json",
    }
    missing_digests = sorted(expected - set(digest_map.keys()))
    if missing_digests:
        raise S2ArtifactError(
            "DIGEST_MISMATCH",
            "run_digests missing artifact hashes",
            {"missing_fields": missing_digests, "artifact": "run_digests.json"},
        )

    for artifact_name in sorted(expected):
        artifact_path = root / artifact_name
        actual_sha = sha256_hex_file(artifact_path)
        expected_sha = str(digest_map.get(artifact_name))
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

    replay_identity = manifest.get("replay_identity")
    if not isinstance(replay_identity, dict):
        raise S2ArtifactError(
            "SCHEMA_INVALID",
            "manifest replay_identity invalid",
            {"artifact": "paper_run_manifest.json"},
        )
    replay_digest = str(replay_identity.get("digest_sha256") or "")
    digest_from_map = str(run_digests.get("replay_identity_digest_sha256") or "")
    if replay_digest != digest_from_map:
        raise S2ArtifactError(
            "DIGEST_MISMATCH",
            "replay identity digest mismatch",
            {"artifact": "run_digests.json"},
        )

    return {
        "run_dir": str(root),
        "run_id": manifest["run_id"],
        "artifact_sha256": dict(digest_map),
        "replay_identity_digest_sha256": replay_digest,
    }
