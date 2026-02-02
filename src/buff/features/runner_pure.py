"""Pure deterministic feature runner."""

from __future__ import annotations

from typing import Mapping, Sequence

import pandas as pd

from buff.data.contracts import REQUIRED_COLUMNS, validate_ohlcv
from buff.features.contract import (
    FeatureContractError,
    FeatureManifestEntry,
    FeatureSpec,
    FeatureValidationError,
    InsufficientLookbackError,
    build_manifest_entries,
    sort_specs,
)
from buff.features.registry import FEATURES


def _resolve_registry_entry(feature_id: str) -> Mapping[str, object]:
    entry = FEATURES.get(feature_id)
    if entry is None:
        raise FeatureContractError("feature_unknown_id")
    return entry


def _validate_spec_params(spec: FeatureSpec, entry: Mapping[str, object]) -> dict[str, object]:
    registry_params = dict(entry.get("params", {}))
    allowed = set(registry_params.keys())
    extra = set(spec.params.keys()) - allowed
    if extra:
        raise FeatureValidationError("feature_params_invalid")
    merged = dict(registry_params)
    merged.update(spec.params)
    return merged


def _ensure_required_columns(df: pd.DataFrame, spec: FeatureSpec) -> None:
    missing = [col for col in spec.requires if col not in df.columns]
    if missing:
        raise FeatureContractError("feature_missing_required_columns")


def run_features_pure(
    market_data_df: pd.DataFrame,
    specs: Sequence[FeatureSpec],
    *,
    validate_contract: bool = True,
) -> tuple[pd.DataFrame, list[FeatureManifestEntry]]:
    if not isinstance(market_data_df, pd.DataFrame):
        raise FeatureContractError("feature_input_invalid")

    missing = [col for col in REQUIRED_COLUMNS if col not in market_data_df.columns]
    if missing:
        raise FeatureContractError("feature_missing_required_columns")

    try:
        input_df = validate_ohlcv(market_data_df)
    except ValueError as exc:
        raise FeatureContractError("feature_input_invalid") from exc

    spec_list = list(specs)
    if validate_contract:
        for spec in spec_list:
            if not isinstance(spec, FeatureSpec):
                raise FeatureContractError("feature_spec_invalid")
            _ = spec.canonical_params_json_bytes()

    ordered_specs = sort_specs(spec_list)

    features: dict[str, pd.Series] = {}
    output_columns: list[str] = []
    seen_outputs: set[str] = set()

    for spec in ordered_specs:
        entry = _resolve_registry_entry(spec.feature_id)

        if spec.lookback > len(input_df):
            raise InsufficientLookbackError("insufficient_lookback")

        if validate_contract:
            _ensure_required_columns(input_df, spec)
            params = _validate_spec_params(spec, entry)
        else:
            params = dict(spec.params)

        result = entry["func"](input_df, **params)

        outputs = list(spec.outputs)
        if isinstance(result, pd.Series):
            if len(outputs) != 1:
                raise FeatureContractError("feature_output_mismatch")
            name = outputs[0]
            if name in seen_outputs:
                raise FeatureContractError("feature_output_conflict")
            features[name] = result
            output_columns.append(name)
            seen_outputs.add(name)
            continue

        if isinstance(result, pd.DataFrame):
            if len(outputs) != len(result.columns):
                raise FeatureContractError("feature_output_mismatch")
            renamed = result.copy()
            renamed.columns = outputs
            for col in outputs:
                if col in seen_outputs:
                    raise FeatureContractError("feature_output_conflict")
                features[col] = renamed[col]
                output_columns.append(col)
                seen_outputs.add(col)
            continue

        raise FeatureContractError("feature_output_type_invalid")

    out = pd.DataFrame(features, index=input_df.index)
    out = out[output_columns]
    return out, build_manifest_entries(ordered_specs)
