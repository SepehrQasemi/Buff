"""Execution contract for strategies (no order placement)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import pandas as pd

from buff.features.bundle import FeatureBundleMetadata
from strategy_registry.decision import Decision, DecisionValidationError, params_hash
from strategy_registry.registry import Strategy, StrategyRegistryError


class StrategyExecutionError(ValueError):
    """Raised when strategy execution contract is violated."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _metadata_features(metadata: FeatureBundleMetadata | Mapping[str, Any]) -> dict[str, dict]:
    if isinstance(metadata, FeatureBundleMetadata):
        return {f"{spec.feature_id}@{spec.version}": spec.to_dict() for spec in metadata.specs}
    payload = dict(metadata)
    features = payload.get("features")
    if not isinstance(features, list):
        raise StrategyExecutionError("strategy_metadata_invalid")
    output: dict[str, dict] = {}
    for spec in features:
        if not isinstance(spec, Mapping):
            raise StrategyExecutionError("strategy_metadata_invalid")
        feature_id = spec.get("feature_id")
        version = spec.get("version")
        if not isinstance(feature_id, str) or not feature_id:
            raise StrategyExecutionError("strategy_metadata_invalid")
        if not isinstance(version, (int, str)) or isinstance(version, bool):
            raise StrategyExecutionError("strategy_metadata_invalid")
        output[f"{feature_id}@{version}"] = dict(spec)
    return output


def _metadata_fingerprint(metadata: FeatureBundleMetadata | Mapping[str, Any]) -> str:
    if isinstance(metadata, FeatureBundleMetadata):
        return metadata.bundle_fingerprint
    payload = dict(metadata)
    fingerprint = payload.get("bundle_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise StrategyExecutionError("strategy_metadata_invalid")
    return fingerprint


def _required_outputs(specs: Mapping[str, dict], required_features: Sequence[str]) -> set[str]:
    required: set[str] = set()
    for feature_id in required_features:
        spec = specs.get(feature_id)
        if spec is None:
            raise StrategyExecutionError("strategy_missing_features")
        outputs = spec.get("outputs", [])
        if not isinstance(outputs, list):
            raise StrategyExecutionError("strategy_metadata_invalid")
        required.update(str(col) for col in outputs)
    return required


def _infer_instrument(
    features_df: pd.DataFrame, metadata: FeatureBundleMetadata | Mapping[str, Any]
) -> str:
    if "instrument" in features_df.attrs:
        value = features_df.attrs.get("instrument")
        if isinstance(value, str) and value:
            return value
    if isinstance(metadata, Mapping):
        value = metadata.get("instrument")
        if isinstance(value, str) and value:
            return value
    raise StrategyExecutionError("strategy_instrument_missing")


def run_strategy(
    strategy: Strategy,
    features_df: pd.DataFrame,
    metadata: FeatureBundleMetadata | Mapping[str, Any],
    as_of_utc: str,
) -> Decision:
    if not isinstance(features_df, pd.DataFrame):
        raise StrategyExecutionError("strategy_features_invalid")
    if not isinstance(as_of_utc, str) or not as_of_utc:
        raise StrategyExecutionError("strategy_as_of_invalid")

    try:
        spec = strategy.spec
    except Exception as exc:  # pragma: no cover - defensive
        raise StrategyRegistryError("strategy_invalid") from exc

    specs = _metadata_features(metadata)
    required_outputs = _required_outputs(specs, spec.required_features)
    missing_outputs = sorted(col for col in required_outputs if col not in features_df.columns)
    if missing_outputs:
        raise StrategyExecutionError("strategy_missing_features")

    decision = strategy.run(features_df, metadata, as_of_utc)
    if not isinstance(decision, Decision):
        raise StrategyExecutionError("strategy_decision_invalid")

    try:
        _ = decision.to_dict()
    except DecisionValidationError as exc:
        raise StrategyExecutionError(str(exc)) from exc

    expected_strategy_id = f"{spec.name}@{spec.version}"
    if decision.provenance.strategy_id != expected_strategy_id:
        raise StrategyExecutionError("strategy_provenance_invalid")

    expected_hash = params_hash(spec.params)
    if decision.provenance.strategy_params_hash != expected_hash:
        raise StrategyExecutionError("strategy_provenance_invalid")

    expected_fingerprint = _metadata_fingerprint(metadata)
    if decision.provenance.feature_bundle_fingerprint != expected_fingerprint:
        raise StrategyExecutionError("strategy_provenance_invalid")

    instrument = _infer_instrument(features_df, metadata)
    if decision.instrument != instrument:
        raise StrategyExecutionError("strategy_instrument_invalid")

    if decision.as_of_utc != as_of_utc:
        raise StrategyExecutionError("strategy_as_of_invalid")

    return decision
