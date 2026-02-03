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
class FeatureDependency:
    name: str
    version: int | str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise FeatureContractError("feature_dependency_name_invalid")
        if not isinstance(self.version, (int, str)) or isinstance(self.version, bool):
            raise FeatureContractError("feature_dependency_version_invalid")

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version}


@dataclass(frozen=True)
class FeatureSpec:
    feature_id: str
    version: int | str = 1
    description: str = ""
    params: Mapping[str, Any] = field(default_factory=dict)
    lookback: int = 0
    lookback_timedelta: str | None = None
    requires: Sequence[str] = field(default_factory=tuple)
    dependencies: Sequence[FeatureDependency] = field(default_factory=tuple)
    outputs: Sequence[str] = field(default_factory=tuple)
    output_dtypes: Mapping[str, str] = field(default_factory=dict)
    input_timeframe: str | None = "1m"

    def __post_init__(self) -> None:
        if not isinstance(self.feature_id, str) or not self.feature_id:
            raise FeatureContractError("feature_id_required")
        if not isinstance(self.version, (int, str)) or isinstance(self.version, bool):
            raise FeatureContractError("feature_version_invalid")
        if not isinstance(self.description, str):
            raise FeatureContractError("feature_description_invalid")
        if (
            not isinstance(self.lookback, int)
            or isinstance(self.lookback, bool)
            or self.lookback < 0
        ):
            raise FeatureContractError("feature_lookback_invalid")
        if self.lookback_timedelta is not None and (
            not isinstance(self.lookback_timedelta, str) or not self.lookback_timedelta
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

        deps = tuple(self.dependencies or ())
        for dep in deps:
            if not isinstance(dep, FeatureDependency):
                raise FeatureContractError("feature_dependencies_invalid")

        output_dtypes = dict(self.output_dtypes or {})
        if output_dtypes:
            for key, value in output_dtypes.items():
                if not isinstance(key, str) or not key:
                    raise FeatureContractError("feature_output_dtypes_invalid")
                if not isinstance(value, str) or not value:
                    raise FeatureContractError("feature_output_dtypes_invalid")
            if set(output_dtypes.keys()) != set(outputs):
                raise FeatureContractError("feature_output_dtypes_invalid")
        elif outputs:
            output_dtypes = {name: "float64" for name in outputs}

        input_timeframe = self.input_timeframe or "1m"
        if not isinstance(input_timeframe, str) or not input_timeframe:
            raise FeatureContractError("feature_input_timeframe_invalid")

        object.__setattr__(self, "params", params)
        object.__setattr__(self, "requires", requires)
        object.__setattr__(self, "outputs", outputs)
        object.__setattr__(self, "dependencies", deps)
        object.__setattr__(self, "output_dtypes", output_dtypes)
        object.__setattr__(self, "input_timeframe", input_timeframe)

    @property
    def name(self) -> str:
        return self.feature_id

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
            schema_version=2,
            feature_id=self.feature_id,
            version=self.version,
            description=self.description,
            params_canonical_json=self.canonical_params_json(),
            lookback=self.lookback,
            lookback_timedelta=self.lookback_timedelta,
            requires=self.requires,
            dependencies=self.dependencies,
            outputs=self.outputs,
            output_dtypes=self.output_dtypes,
            input_timeframe=self.input_timeframe,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "version": self.version,
            "description": self.description,
            "params": dict(self.params),
            "lookback": self.lookback,
            "lookback_timedelta": self.lookback_timedelta,
            "requires": list(self.requires),
            "dependencies": [dep.to_dict() for dep in self.dependencies],
            "outputs": list(self.outputs),
            "output_dtypes": dict(self.output_dtypes),
            "input_timeframe": self.input_timeframe,
        }


@dataclass(frozen=True)
class FeatureManifestEntry:
    schema_version: int
    feature_id: str
    version: int | str
    params_canonical_json: str
    lookback: int
    description: str = ""
    lookback_timedelta: str | None = None
    requires: Sequence[str] = field(default_factory=tuple)
    dependencies: Sequence[FeatureDependency] = field(default_factory=tuple)
    outputs: Sequence[str] = field(default_factory=tuple)
    output_dtypes: Mapping[str, str] = field(default_factory=dict)
    input_timeframe: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version not in {1, 2}:
            raise FeatureContractError("feature_manifest_schema_invalid")
        if not isinstance(self.feature_id, str) or not self.feature_id:
            raise FeatureContractError("feature_id_required")
        if not isinstance(self.version, (int, str)) or isinstance(self.version, bool):
            raise FeatureContractError("feature_version_invalid")
        if not isinstance(self.description, str):
            raise FeatureContractError("feature_description_invalid")
        if (
            not isinstance(self.lookback, int)
            or isinstance(self.lookback, bool)
            or self.lookback < 0
        ):
            raise FeatureContractError("feature_lookback_invalid")
        if self.lookback_timedelta is not None and (
            not isinstance(self.lookback_timedelta, str) or not self.lookback_timedelta
        ):
            raise FeatureContractError("feature_lookback_invalid")
        if not isinstance(self.params_canonical_json, str):
            raise FeatureContractError("feature_params_invalid")

        requires = tuple(self.requires or ())
        outputs = tuple(self.outputs or ())
        dependencies = tuple(self.dependencies or ())
        output_dtypes = dict(self.output_dtypes or {})
        for dep in dependencies:
            if not isinstance(dep, FeatureDependency):
                raise FeatureContractError("feature_dependencies_invalid")
        if output_dtypes:
            for key, value in output_dtypes.items():
                if not isinstance(key, str) or not key:
                    raise FeatureContractError("feature_output_dtypes_invalid")
                if not isinstance(value, str) or not value:
                    raise FeatureContractError("feature_output_dtypes_invalid")
            if outputs and set(output_dtypes.keys()) != set(outputs):
                raise FeatureContractError("feature_output_dtypes_invalid")
        object.__setattr__(self, "requires", requires)
        object.__setattr__(self, "outputs", outputs)
        object.__setattr__(self, "dependencies", dependencies)
        object.__setattr__(self, "output_dtypes", output_dtypes)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "feature_id": self.feature_id,
            "version": self.version,
            "description": self.description,
            "params_canonical_json": self.params_canonical_json,
            "lookback": self.lookback,
            "lookback_timedelta": self.lookback_timedelta,
            "requires": list(self.requires),
            "dependencies": [dep.to_dict() for dep in self.dependencies],
            "outputs": list(self.outputs),
            "output_dtypes": dict(self.output_dtypes),
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
        description = str(spec.get("description") or f"{feature_id} feature")
        output_dtypes = {name: "float64" for name in outputs}
        kind = spec.get("kind")
        version = spec.get("version", 1)
        lookback = infer_lookback(kind, params)
        specs.append(
            FeatureSpec(
                feature_id=feature_id,
                version=version,
                description=description,
                params=params,
                lookback=lookback,
                requires=requires,
                outputs=outputs,
                output_dtypes=output_dtypes,
            )
        )
    return specs


def sort_specs(specs: Iterable[FeatureSpec]) -> list[FeatureSpec]:
    return sorted(list(specs), key=lambda spec: spec.canonical_key())


def build_manifest_entries(specs: Iterable[FeatureSpec]) -> list[FeatureManifestEntry]:
    ordered = sort_specs(specs)
    return [spec.to_manifest_entry() for spec in ordered]
