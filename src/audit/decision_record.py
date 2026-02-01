from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import Any, Mapping

from audit.canonical_json import canonical_json_bytes


def _sha256_hex(data: bytes) -> str:
    return f"sha256:{sha256(data).hexdigest()}"


def _require_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _require_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    return value


def _require_list_str(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field} entries must be strings")
    return value


def _require_dict(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a dict")
    for key in value.keys():
        if not isinstance(key, str):
            raise ValueError(f"{field} keys must be strings")
    return value


def _require_iso8601_utc(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601") from exc
    if dt.tzinfo is None:
        raise ValueError(f"{field} must include timezone")
    return value


@dataclass(frozen=True)
class CodeVersion:
    git_commit: str
    dirty: bool

    def __post_init__(self) -> None:
        _require_str(self.git_commit, "code_version.git_commit")
        _require_bool(self.dirty, "code_version.dirty")


@dataclass(frozen=True)
class RunContext:
    seed: int
    python: str
    platform: str

    def __post_init__(self) -> None:
        _require_int(self.seed, "run_context.seed")
        _require_str(self.python, "run_context.python")
        _require_str(self.platform, "run_context.platform")


@dataclass(frozen=True)
class Artifacts:
    snapshot_ref: str | None
    features_ref: str | None

    def __post_init__(self) -> None:
        if self.snapshot_ref is not None:
            _require_str(self.snapshot_ref, "artifacts.snapshot_ref")
        if self.features_ref is not None:
            _require_str(self.features_ref, "artifacts.features_ref")


@dataclass(frozen=True)
class Inputs:
    market_features: dict[str, Any]
    risk_state: str
    selector_inputs: dict[str, Any]
    config: dict[str, Any]
    risk_mode: str

    def __post_init__(self) -> None:
        _require_dict(self.market_features, "inputs.market_features")
        _require_str(self.risk_state, "inputs.risk_state")
        _require_dict(self.selector_inputs, "inputs.selector_inputs")
        _require_dict(self.config, "inputs.config")
        _require_str(self.risk_mode, "inputs.risk_mode")
        if self.risk_mode not in {"fact", "computed"}:
            raise ValueError("inputs.risk_mode must be fact|computed")


@dataclass(frozen=True)
class Selection:
    selected: bool
    strategy_id: str | None
    status: str
    score: float | int | None
    reasons: list[str] = field(default_factory=list)
    rules_fired: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _require_bool(self.selected, "selection.selected")
        if self.strategy_id is not None:
            _require_str(self.strategy_id, "selection.strategy_id")
        _require_str(self.status, "selection.status")
        if self.status not in {"selected", "no_selection", "blocked"}:
            raise ValueError("selection.status must be selected|no_selection|blocked")
        if self.status == "selected" and not self.selected:
            raise ValueError("selection.selected must be true when status=selected")
        if self.status in {"no_selection", "blocked"} and self.selected:
            raise ValueError("selection.selected must be false when status!=selected")
        if self.selected and self.strategy_id is None:
            raise ValueError("selection.strategy_id is required when selected")
        if not self.selected and self.strategy_id is not None:
            raise ValueError("selection.strategy_id must be null when not selected")
        if self.score is not None and not isinstance(self.score, (int, float)):
            raise ValueError("selection.score must be a number or null")
        reasons = _require_list_str(self.reasons, "selection.reasons")
        rules = _require_list_str(self.rules_fired, "selection.rules_fired")
        reasons_sorted = sorted(reasons)
        rules_sorted = sorted(rules)
        object.__setattr__(self, "reasons", reasons_sorted)
        object.__setattr__(self, "rules_fired", rules_sorted)


@dataclass(frozen=True)
class Outcome:
    decision: str
    allowed: bool
    notes: str | None

    def __post_init__(self) -> None:
        _require_str(self.decision, "outcome.decision")
        _require_bool(self.allowed, "outcome.allowed")
        if self.notes is not None:
            _require_str(self.notes, "outcome.notes")


@dataclass(frozen=True)
class Hashes:
    core_hash: str
    content_hash: str
    inputs_hash: str | None = None

    def __post_init__(self) -> None:
        _require_str(self.core_hash, "hashes.core_hash")
        _require_str(self.content_hash, "hashes.content_hash")
        if self.inputs_hash is not None:
            _require_str(self.inputs_hash, "hashes.inputs_hash")


@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str
    ts_utc: str
    symbol: str
    timeframe: str
    code_version: CodeVersion
    run_context: RunContext
    artifacts: Artifacts
    inputs: Inputs
    selection: Selection
    outcome: Outcome
    hashes: Hashes | None = None

    def __post_init__(self) -> None:
        _require_str(self.decision_id, "decision_id")
        _require_iso8601_utc(self.ts_utc, "ts_utc")
        _require_str(self.symbol, "symbol")
        _require_str(self.timeframe, "timeframe")

        computed = self._compute_hashes()
        if self.hashes is None:
            object.__setattr__(self, "hashes", computed)
        else:
            if (
                self.hashes.core_hash != computed.core_hash
                or self.hashes.content_hash != computed.content_hash
                or self.hashes.inputs_hash != computed.inputs_hash
            ):
                raise ValueError("hashes do not match computed values")

    def _full_payload(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "ts_utc": self.ts_utc,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "code_version": asdict(self.code_version),
            "run_context": asdict(self.run_context),
            "artifacts": asdict(self.artifacts),
            "inputs": asdict(self.inputs),
            "selection": asdict(self.selection),
            "outcome": asdict(self.outcome),
        }

    def _core_payload(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "artifacts": {
                "snapshot_ref": self.artifacts.snapshot_ref,
                "features_ref": self.artifacts.features_ref,
            },
            "inputs": asdict(self.inputs),
            "selection": asdict(self.selection),
            "outcome": asdict(self.outcome),
        }

    def _compute_hashes(self) -> Hashes:
        inputs_hash = _sha256_hex(canonical_json_bytes(asdict(self.inputs)))
        core_hash = _sha256_hex(canonical_json_bytes(self._core_payload()))
        content_hash = _sha256_hex(canonical_json_bytes(self._full_payload()))
        return Hashes(core_hash=core_hash, content_hash=content_hash, inputs_hash=inputs_hash)

    def to_dict(self) -> dict[str, Any]:
        if self.hashes is None:
            hashes = self._compute_hashes()
        else:
            hashes = self.hashes
        payload = self._full_payload()
        payload["hashes"] = {
            "core_hash": hashes.core_hash,
            "content_hash": hashes.content_hash,
            "inputs_hash": hashes.inputs_hash,
        }
        return payload

    def to_canonical_json(self) -> str:
        return canonical_json_bytes(self.to_dict()).decode("utf-8")

    def canonicalize_core(self) -> bytes:
        return canonical_json_bytes(self._core_payload())

    def canonicalize_full(self) -> bytes:
        return canonical_json_bytes(self._full_payload())

    def compute_core_hash(self) -> str:
        return _sha256_hex(self.canonicalize_core())

    def compute_content_hash(self) -> str:
        return _sha256_hex(self.canonicalize_full())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DecisionRecord":
        if not isinstance(payload, Mapping):
            raise ValueError("payload must be a mapping")
        code_version = payload.get("code_version", {})
        run_context = payload.get("run_context", {})
        artifacts = payload.get("artifacts", {})
        inputs = payload.get("inputs", {})
        selection = payload.get("selection", {})
        outcome = payload.get("outcome", {})
        hashes = payload.get("hashes")

        return cls(
            decision_id=payload.get("decision_id"),
            ts_utc=payload.get("ts_utc"),
            symbol=payload.get("symbol"),
            timeframe=payload.get("timeframe"),
            code_version=CodeVersion(
                git_commit=code_version.get("git_commit"),
                dirty=code_version.get("dirty"),
            ),
            run_context=RunContext(
                seed=run_context.get("seed"),
                python=run_context.get("python"),
                platform=run_context.get("platform"),
            ),
            artifacts=Artifacts(
                snapshot_ref=artifacts.get("snapshot_ref"),
                features_ref=artifacts.get("features_ref"),
            ),
            inputs=Inputs(
                market_features=inputs.get("market_features", {}),
                risk_state=inputs.get("risk_state"),
                selector_inputs=inputs.get("selector_inputs", {}),
                config=inputs.get("config", {}),
                risk_mode=inputs.get("risk_mode"),
            ),
            selection=Selection(
                selected=selection.get("selected"),
                strategy_id=selection.get("strategy_id"),
                status=selection.get("status"),
                score=selection.get("score"),
                reasons=selection.get("reasons", []),
                rules_fired=selection.get("rules_fired", []),
            ),
            outcome=Outcome(
                decision=outcome.get("decision"),
                allowed=outcome.get("allowed"),
                notes=outcome.get("notes"),
            ),
            hashes=Hashes(
                core_hash=hashes.get("core_hash"),
                content_hash=hashes.get("content_hash"),
                inputs_hash=hashes.get("inputs_hash"),
            )
            if isinstance(hashes, Mapping)
            else None,
        )


def canonicalize_core(record: DecisionRecord | Mapping[str, Any]) -> bytes:
    if isinstance(record, DecisionRecord):
        return record.canonicalize_core()
    return DecisionRecord.from_dict(record).canonicalize_core()


def canonicalize_full(record: DecisionRecord | Mapping[str, Any]) -> bytes:
    if isinstance(record, DecisionRecord):
        return record.canonicalize_full()
    return DecisionRecord.from_dict(record).canonicalize_full()


def canonicalize_core_payload(payload: Mapping[str, Any]) -> bytes:
    cleaned = dict(payload)
    cleaned.pop("hashes", None)
    return DecisionRecord.from_dict(cleaned).canonicalize_core()


def compute_core_hash(record: DecisionRecord | Mapping[str, Any]) -> str:
    if isinstance(record, DecisionRecord):
        return record.compute_core_hash()
    return DecisionRecord.from_dict(record).compute_core_hash()


def compute_content_hash(record: DecisionRecord | Mapping[str, Any]) -> str:
    if isinstance(record, DecisionRecord):
        return record.compute_content_hash()
    return DecisionRecord.from_dict(record).compute_content_hash()
