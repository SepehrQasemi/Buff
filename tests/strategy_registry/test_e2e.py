from __future__ import annotations

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
from strategy_registry.execution import run_strategy
from strategy_registry.registry import StrategyDefinition, StrategyRegistry, StrategySpec
from strategy_registry.selector import SelectorConfig, select_strategy
from tests.fixtures.ohlcv_factory import make_ohlcv


def test_end_to_end_strategy_flow() -> None:
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

    def _runner(features_frame, meta, as_of_utc) -> Decision:
        return Decision(
            schema_version=DECISION_SCHEMA_VERSION,
            as_of_utc=as_of_utc,
            instrument="BTCUSDT",
            action=DecisionAction.HOLD,
            rationale=["no_signal"],
            risk=DecisionRisk(max_position_size=1.0, stop_loss=0.01, take_profit=0.02),
            provenance=DecisionProvenance(
                feature_bundle_fingerprint=meta.bundle_fingerprint,
                strategy_id="demo@1.0.0",
                strategy_params_hash=params_hash(spec.params),
            ),
        )

    registry = StrategyRegistry()
    registry.register(StrategyDefinition(spec=spec, runner=_runner))

    selector_config = SelectorConfig(
        schema_version=1,
        allowed_strategy_ids=["demo@1.0.0"],
        mode="fixed",
        fixed_strategy_id="demo@1.0.0",
    )
    selection = select_strategy(
        selector_config,
        market_state={"regime_id": "trend"},
        registry=registry,
        metadata=metadata.to_dict(),
    )

    strategy = registry.get(selection.chosen_strategy_id or "")
    decision = run_strategy(strategy, features_df, metadata, metadata.time_bounds.as_of_utc)
    assert decision.provenance.feature_bundle_fingerprint == metadata.bundle_fingerprint
