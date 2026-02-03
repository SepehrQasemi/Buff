from __future__ import annotations

import builtins
from pathlib import Path

import pandas as pd
import pytest

from buff.features.bundle import (
    FeatureBundleMetadata,
    compute_features,
    validate_feature_bundle,
)
from buff.features.contract import FeatureDependency, FeatureSpec, build_feature_specs_from_registry
from buff.features.registry import FEATURES
from tests.fixtures.ohlcv_factory import make_ohlcv


def _prepare_df(rows: int = 120) -> pd.DataFrame:
    df = make_ohlcv(rows)
    df.attrs["run_id"] = "run-test"
    df.attrs["as_of_utc"] = "2025-01-01T00:00:00Z"
    df.attrs["created_at_utc"] = "2025-01-01T00:00:00Z"
    return df


def test_compute_features_metadata_fields() -> None:
    df = _prepare_df()
    specs = build_feature_specs_from_registry(FEATURES)
    _, metadata = compute_features(df, specs)

    assert isinstance(metadata, FeatureBundleMetadata)
    assert metadata.schema_version == 1
    assert metadata.run_id == "run-test"
    assert metadata.time_bounds.as_of_utc == "2025-01-01T00:00:00Z"
    assert metadata.source_fingerprint
    assert metadata.bundle_fingerprint
    assert metadata.specs
    assert metadata.dependency_graph


def test_dependency_graph_ordering() -> None:
    df = _prepare_df()
    specs = [
        FeatureSpec(
            feature_id="ema_20",
            version=1,
            description="ema",
            params={"period": 20},
            lookback=19,
            requires=["close"],
            dependencies=[FeatureDependency(name="sma_20", version=1)],
            outputs=["ema_20"],
        ),
        FeatureSpec(
            feature_id="sma_20",
            version=1,
            description="sma",
            params={"period": 20},
            lookback=19,
            requires=["close"],
            outputs=["sma_20"],
        ),
    ]
    _, metadata = compute_features(df, specs)
    keys = list(metadata.dependency_graph.keys())
    assert keys == sorted(keys)


def test_compute_features_deterministic() -> None:
    df = _prepare_df()
    specs = build_feature_specs_from_registry(FEATURES)
    out_a, meta_a = compute_features(df, specs)
    out_b, meta_b = compute_features(df, specs)

    pd.testing.assert_frame_equal(out_a, out_b, check_dtype=True)
    assert meta_a.to_dict() == meta_b.to_dict()


def test_validate_feature_bundle_schema_mismatch() -> None:
    df = _prepare_df()
    specs = build_feature_specs_from_registry(FEATURES)
    out, meta = compute_features(df, specs)
    payload = meta.to_dict()
    payload["schema_version"] = 0
    with pytest.raises(ValueError):
        validate_feature_bundle(out, payload)


def test_compute_features_no_io(monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_io(*args: object, **kwargs: object) -> None:
        raise AssertionError("io_not_allowed")

    monkeypatch.setattr(builtins, "open", _no_io)
    monkeypatch.setattr(Path, "write_text", _no_io)
    monkeypatch.setattr(Path, "write_bytes", _no_io)

    df = _prepare_df()
    specs = build_feature_specs_from_registry(FEATURES)
    _, metadata = compute_features(df, specs)
    assert metadata.schema_version == 1


def test_validate_feature_bundle_nan_policy() -> None:
    df = _prepare_df()
    specs = build_feature_specs_from_registry({name: FEATURES[name] for name in ["ema_20"]})
    out, meta = compute_features(df, specs)

    out.loc[out.index[30], "ema_20"] = float("nan")
    with pytest.raises(ValueError):
        validate_feature_bundle(out, meta)
