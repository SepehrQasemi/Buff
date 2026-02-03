from __future__ import annotations

import pytest

from buff.features.bundle import compute_features
from buff.features.contract import build_feature_specs_from_registry
from buff.features.registry import FEATURES
from strategy_registry.decision import (
    DECISION_SCHEMA_VERSION,
    Decision,
    DecisionAction,
    DecisionProvenance,
    DecisionRisk,
    params_hash,
)
from strategy_registry.execution import StrategyExecutionError, run_strategy
from strategy_registry.registry import StrategyDefinition, StrategySpec
from tests.fixtures.ohlcv_factory import make_ohlcv


def _strategy(spec: StrategySpec) -> StrategyDefinition:
    strategy_id = f"{spec.name}@{spec.version}"

    def _runner(features_df, metadata, as_of_utc):
        return Decision(
            schema_version=DECISION_SCHEMA_VERSION,
            as_of_utc=as_of_utc,
            instrument="BTCUSDT",
            action=DecisionAction.HOLD,
            rationale=["no_signal"],
            risk=DecisionRisk(max_position_size=1.0, stop_loss=0.01, take_profit=0.02),
            provenance=DecisionProvenance(
                feature_bundle_fingerprint=metadata.bundle_fingerprint,
                strategy_id=strategy_id,
                strategy_params_hash=params_hash(spec.params),
            ),
        )

    return StrategyDefinition(spec=spec, runner=_runner)


def test_run_strategy_emits_decision_with_provenance() -> None:
    df = make_ohlcv(120)
    specs = build_feature_specs_from_registry(FEATURES)
    features_df, metadata = compute_features(df, specs)
    features_df.attrs["instrument"] = "BTCUSDT"

    required_feature = f"{metadata.specs[0].feature_id}@{metadata.specs[0].version}"
    spec = StrategySpec(
        name="demo",
        version="1.0.0",
        description="demo",
        required_features=[required_feature],
        required_timeframes=["1m"],
        params={"alpha": 1},
    )

    decision = run_strategy(_strategy(spec), features_df, metadata, metadata.time_bounds.as_of_utc)
    assert decision.provenance.feature_bundle_fingerprint == metadata.bundle_fingerprint
    assert decision.provenance.strategy_id == "demo@1.0.0"


def test_run_strategy_missing_features_fails() -> None:
    df = make_ohlcv(120)
    specs = build_feature_specs_from_registry(FEATURES)
    features_df, metadata = compute_features(df, specs)
    features_df.attrs["instrument"] = "BTCUSDT"

    spec = StrategySpec(
        name="demo",
        version="1.0.0",
        description="demo",
        required_features=["missing@1"],
        required_timeframes=["1m"],
        params={},
    )
    with pytest.raises(StrategyExecutionError):
        run_strategy(_strategy(spec), features_df, metadata, metadata.time_bounds.as_of_utc)
