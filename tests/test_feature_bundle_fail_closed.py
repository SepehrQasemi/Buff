from __future__ import annotations

import pytest

from buff.features.bundle import (
    FeatureBundleValidationError,
    compute_features,
    validate_feature_bundle,
)
from buff.features.contract import build_feature_specs_from_registry
from buff.features.registry import FEATURES
from tests.fixtures.ohlcv_factory import make_ohlcv


def test_feature_bundle_missing_output_column_fails() -> None:
    df = make_ohlcv(120)
    specs = build_feature_specs_from_registry(FEATURES)
    features_df, metadata = compute_features(df, specs)

    missing_col = metadata.specs[0].outputs[0]
    broken = features_df.drop(columns=[missing_col])
    with pytest.raises(FeatureBundleValidationError):
        validate_feature_bundle(broken, metadata)


def test_feature_bundle_schema_version_invalid_fails() -> None:
    df = make_ohlcv(120)
    specs = build_feature_specs_from_registry(FEATURES)
    features_df, metadata = compute_features(df, specs)
    payload = metadata.to_dict()
    payload["schema_version"] = 999
    with pytest.raises(FeatureBundleValidationError):
        validate_feature_bundle(features_df, payload)
