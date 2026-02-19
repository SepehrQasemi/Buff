"""Deterministic core risk policy packs (v1)."""

from __future__ import annotations

from risk.contracts import RiskConfig, RiskState

L1_CONSERVATIVE = RiskConfig(
    pack_id="L1_CONSERVATIVE",
    pack_version="v1",
    config_version="risk-pack:L1_CONSERVATIVE@v1",
    missing_red=0.08,
    atr_yellow=0.012,
    atr_red=0.02,
    rvol_yellow=0.012,
    rvol_red=0.02,
    max_missing_fraction=0.08,
    yellow_atr_pct=0.008,
    red_atr_pct=0.015,
    yellow_vol=0.008,
    red_vol=0.015,
    recommended_scale_yellow=0.2,
    no_metrics_state=RiskState.RED,
)

L3_BALANCED = RiskConfig(
    pack_id="L3_BALANCED",
    pack_version="v1",
    config_version="risk-pack:L3_BALANCED@v1",
    missing_red=0.2,
    atr_yellow=0.02,
    atr_red=0.05,
    rvol_yellow=0.02,
    rvol_red=0.05,
    max_missing_fraction=0.2,
    yellow_atr_pct=0.01,
    red_atr_pct=0.02,
    yellow_vol=0.01,
    red_vol=0.02,
    recommended_scale_yellow=0.25,
    no_metrics_state=RiskState.YELLOW,
)

L5_AGGRESSIVE = RiskConfig(
    pack_id="L5_AGGRESSIVE",
    pack_version="v1",
    config_version="risk-pack:L5_AGGRESSIVE@v1",
    missing_red=0.35,
    atr_yellow=0.04,
    atr_red=0.08,
    rvol_yellow=0.04,
    rvol_red=0.08,
    max_missing_fraction=0.35,
    yellow_atr_pct=0.02,
    red_atr_pct=0.04,
    yellow_vol=0.02,
    red_vol=0.04,
    recommended_scale_yellow=0.5,
    no_metrics_state=RiskState.YELLOW,
)
