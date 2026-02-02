"""Feature contract models and helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from buff.features.canonical import canonical_json_bytes, canonical_json_str


class FeatureError(ValueError):
    """Base error for feature contract violations."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class FeatureContractError(FeatureError):
    """Raised when the feature contract is violated."""


class FeatureValidationError(FeatureError):
    """Raised when feature validation fails deterministically."""


class InsufficientLookbackError(FeatureError):
    """Raised when the input window is shorter than required lookback."""


@dataclass(frozen=True)
class FeatureSpec:
    feature_id: str
    version: int | str = 1
    params: Mapping[str, Any] = field(default_factory=dict)
    lookback: int = 0
    requires: Sequence[str] = field(default_factory=tuple)
    outputs: Sequence[str] = field(default_factory=tuple)
    input_timeframe: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.feature_id, str) or not self.feature_id:
            raise FeatureContractError("feature_id_required")
        if not isinstance(self.version, (int, str)) or isinstance(self.version, bool):
            raise FeatureContractError("feature_version_invalid")
        if (
            not isinstance(self.lookback, int)
            or isinstance(self.lookback, bool)
            or self.lookback < 0
        ):
            raise FeatureContractError("feature_lookback_invalid")

        params = dict(self.params or {})
        for key in params.keys():
            if not isinstance(key, str):
                raise FeatureValidationError("feature_params_invalid")

        requires = tuple(self.requires or ())
        for value in requires:
            if not isinstance(value, str) or not value:
                raise FeatureContractError("feature_requires_invalid")

        outputs = tuple(self.outputs or ())
        for value in outputs:
            if not isinstance(value, str) or not value:
                raise FeatureContractError("feature_outputs_invalid")

        if self.input_timeframe is not None and (
            not isinstance(self.input_timeframe, str) or not self.input_timeframe
        ):
            raise FeatureContractError("feature_input_timeframe_invalid")

        object.__setattr__(self, "params", params)
        object.__setattr__(self, "requires", requires)
        object.__setattr__(self, "outputs", outputs)

    def canonical_params_json_bytes(self) -> bytes:
        try:
            return canonical_json_bytes(self.params)
        except (TypeError, ValueError) as exc:
            raise FeatureValidationError("feature_params_invalid") from exc

    def canonical_params_json(self) -> str:
        return canonical_json_str(self.params)

    def canonical_key(self) -> tuple[str, bytes, str]:
        return (self.feature_id, self.canonical_params_json_bytes(), str(self.version))

    def to_manifest_entry(self) -> "FeatureManifestEntry":
        return FeatureManifestEntry(
            schema_version=1,
            feature_id=self.feature_id,
            version=self.version,
            params_canonical_json=self.canonical_params_json(),
            lookback=self.lookback,
            requires=self.requires,
            outputs=self.outputs,
            input_timeframe=self.input_timeframe,
        )


@dataclass(frozen=True)
class FeatureManifestEntry:
    schema_version: int
    feature_id: str
    version: int | str
    params_canonical_json: str
    lookback: int
    requires: Sequence[str] = field(default_factory=tuple)
    outputs: Sequence[str] = field(default_factory=tuple)
    input_timeframe: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise FeatureContractError("feature_manifest_schema_invalid")
        if not isinstance(self.feature_id, str) or not self.feature_id:
            raise FeatureContractError("feature_id_required")
        if not isinstance(self.version, (int, str)) or isinstance(self.version, bool):
            raise FeatureContractError("feature_version_invalid")
        if (
            not isinstance(self.lookback, int)
            or isinstance(self.lookback, bool)
            or self.lookback < 0
        ):
            raise FeatureContractError("feature_lookback_invalid")
        if not isinstance(self.params_canonical_json, str):
            raise FeatureContractError("feature_params_invalid")

        requires = tuple(self.requires or ())
        outputs = tuple(self.outputs or ())
        object.__setattr__(self, "requires", requires)
        object.__setattr__(self, "outputs", outputs)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "feature_id": self.feature_id,
            "version": self.version,
            "params_canonical_json": self.params_canonical_json,
            "lookback": self.lookback,
            "requires": list(self.requires),
            "outputs": list(self.outputs),
        }
        if self.input_timeframe is not None:
            payload["input_timeframe"] = self.input_timeframe
        return payload


@dataclass(frozen=True)
class FeatureResult:
    features: Any
    manifest: Sequence[FeatureManifestEntry]


def infer_lookback(kind: str | None, params: Mapping[str, Any]) -> int:
    if kind in {"ema", "sma", "std", "bbands"}:
        return max(0, int(params.get("period", 0)) - 1)
    if kind in {"rsi", "atr"}:
        return max(0, int(params.get("period", 0)))
    if kind == "macd":
        return max(0, int(params.get("slow", 0)) + int(params.get("signal", 0)) - 2)
    if kind == "ema_spread":
        return max(0, int(params.get("slow", 0)) - 1)
    if kind == "rsi_slope":
        return max(0, (int(params.get("period", 0)) - 1) + int(params.get("slope", 0)))
    if kind == "roc":
        return max(0, int(params.get("period", 0)))
    if kind in {"vwap", "obv"}:
        return 0
    if kind == "adx":
        return max(0, int(params.get("period", 0)) * 2)
    return 0


def build_feature_specs_from_registry(
    registry: Mapping[str, Mapping[str, Any]],
) -> list[FeatureSpec]:
    specs: list[FeatureSpec] = []
    for feature_id, spec in registry.items():
        params = dict(spec.get("params", {}))
        requires = list(spec.get("requires", []))
        outputs = list(spec.get("outputs", []))
        kind = spec.get("kind")
        version = spec.get("version", 1)
        lookback = infer_lookback(kind, params)
        specs.append(
            FeatureSpec(
                feature_id=feature_id,
                version=version,
                params=params,
                lookback=lookback,
                requires=requires,
                outputs=outputs,
            )
        )
    return specs


def sort_specs(specs: Iterable[FeatureSpec]) -> list[FeatureSpec]:
    return sorted(list(specs), key=lambda spec: spec.canonical_key())


def build_manifest_entries(specs: Iterable[FeatureSpec]) -> list[FeatureManifestEntry]:
    ordered = sort_specs(specs)
    return [spec.to_manifest_entry() for spec in ordered]
