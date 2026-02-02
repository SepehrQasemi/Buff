from __future__ import annotations

import builtins
import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from buff.features.contract import (
    FeatureContractError,
    FeatureSpec,
    FeatureValidationError,
    InsufficientLookbackError,
    build_feature_specs_from_registry,
    sort_specs,
)
from buff.features.registry import FEATURES
from buff.features.runner import run_features
from buff.features.runner_pure import run_features_pure
from tests.fixtures.ohlcv_factory import make_ohlcv


def test_run_features_pure_no_io(monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_io(*args: object, **kwargs: object) -> None:
        raise AssertionError("io_not_allowed")

    monkeypatch.setattr(builtins, "open", _no_io)
    monkeypatch.setattr(Path, "write_text", _no_io)
    monkeypatch.setattr(Path, "write_bytes", _no_io)

    df = make_ohlcv(50)
    specs = build_feature_specs_from_registry(
        {name: FEATURES[name] for name in ["ema_20", "rsi_14"]}
    )
    out, manifest = run_features_pure(df, specs)
    assert not out.empty
    assert len(manifest) == 2


def test_run_features_pure_does_not_mutate_inputs() -> None:
    df = make_ohlcv(50)
    df_copy = df.copy(deep=True)
    specs = build_feature_specs_from_registry(
        {name: FEATURES[name] for name in ["ema_20", "rsi_14"]}
    )
    specs_copy = copy.deepcopy(specs)

    _ = run_features_pure(df, specs)

    pd.testing.assert_frame_equal(df, df_copy)
    assert specs == specs_copy


def test_run_features_pure_deterministic_output() -> None:
    df = make_ohlcv(120)
    specs = build_feature_specs_from_registry(
        {name: FEATURES[name] for name in ["ema_20", "rsi_14", "atr_14"]}
    )
    out_a, manifest_a = run_features_pure(df, specs)
    out_b, manifest_b = run_features_pure(df, specs)

    pd.testing.assert_frame_equal(out_a, out_b, check_dtype=True)
    manifest_payload_a = [entry.to_dict() for entry in manifest_a]
    manifest_payload_b = [entry.to_dict() for entry in manifest_b]
    assert manifest_payload_a == manifest_payload_b

    payload_a = out_a.to_csv(index=True, lineterminator="\n", float_format="%.10f")
    payload_b = out_b.to_csv(index=True, lineterminator="\n", float_format="%.10f")
    assert payload_a == payload_b


def test_column_order_stable() -> None:
    df = make_ohlcv(60)
    specs = [
        FeatureSpec(
            feature_id="rsi_14",
            params={"period": 14},
            lookback=14,
            requires=["close"],
            outputs=["rsi_14"],
        ),
        FeatureSpec(
            feature_id="ema_20",
            params={"period": 20},
            lookback=19,
            requires=["close"],
            outputs=["ema_20"],
        ),
    ]

    out, manifest = run_features_pure(df, specs)
    assert list(out.columns) == ["ema_20", "rsi_14"]
    assert [entry.feature_id for entry in manifest] == ["ema_20", "rsi_14"]


def test_manifest_deterministic_and_matches_outputs() -> None:
    df = make_ohlcv(80)
    specs = build_feature_specs_from_registry(
        {name: FEATURES[name] for name in ["ema_20", "bbands_20_2"]}
    )
    out, manifest = run_features_pure(df, specs)

    expected_columns: list[str] = []
    for entry in manifest:
        expected_columns.extend(entry.outputs)
    assert list(out.columns) == expected_columns


def test_rejects_unknown_params_deterministically() -> None:
    df = make_ohlcv(50)
    spec = FeatureSpec(
        feature_id="ema_20",
        params={"period": 20, "extra": 1},
        lookback=19,
        requires=["close"],
        outputs=["ema_20"],
    )
    with pytest.raises(FeatureValidationError) as exc:
        _ = run_features_pure(df, [spec])
    assert str(exc.value) == "feature_params_invalid"


def test_insufficient_lookback_raises_deterministically() -> None:
    df = make_ohlcv(5)
    spec = FeatureSpec(
        feature_id="ema_20",
        params={"period": 20},
        lookback=10,
        requires=["close"],
        outputs=["ema_20"],
    )
    with pytest.raises(InsufficientLookbackError) as exc:
        _ = run_features_pure(df, [spec])
    assert str(exc.value) == "insufficient_lookback"


def test_missing_required_columns_contract_error() -> None:
    df = make_ohlcv(20).drop(columns=["volume"])
    spec = FeatureSpec(
        feature_id="obv",
        params={},
        lookback=0,
        requires=["close", "volume"],
        outputs=["obv"],
    )
    with pytest.raises(FeatureContractError) as exc:
        _ = run_features_pure(df, [spec])
    assert str(exc.value) == "feature_missing_required_columns"


def test_run_features_smoke_from_snapshot_payload() -> None:
    payload = json.loads(Path("tests/fixtures/snapshot_payload.json").read_text(encoding="utf-8"))
    row = payload["market_data"][0]
    base = pd.Timestamp(row["ts"])
    rows = []
    for idx in range(60):
        ts = base + pd.Timedelta(minutes=idx)
        item = dict(row)
        item["timestamp"] = ts.isoformat().replace("+00:00", "Z")
        item.pop("ts", None)
        rows.append(item)
    df = pd.DataFrame(rows)

    out = run_features(df, mode="train")
    ordered_specs = sort_specs(build_feature_specs_from_registry(FEATURES))
    expected_columns = [col for spec in ordered_specs for col in spec.outputs]
    assert list(out.columns) == expected_columns
    assert out.shape[0] == len(df)
