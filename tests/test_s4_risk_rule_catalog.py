from __future__ import annotations

import pandas as pd
import pytest

from risk.contracts import RiskConfig, RiskInputs
from risk.evaluator import evaluate_risk_report
from risk.packs.core import L1_CONSERVATIVE, L3_BALANCED, L5_AGGRESSIVE
from risk.rule_catalog import ALL_RULE_IDS, RiskRuleId
from risk.state_machine import evaluate_risk
from risk.veto import risk_veto


pytestmark = pytest.mark.unit


def _inputs(**overrides: object) -> RiskInputs:
    payload = {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "as_of": "2024-01-01T00:00:00+00:00",
        "atr_pct": 0.01,
        "realized_vol": 0.01,
        "missing_fraction": 0.0,
        "timestamps_valid": True,
        "latest_metrics_valid": True,
        "invalid_index": False,
        "invalid_close": False,
    }
    payload.update(overrides)
    return RiskInputs(**payload)


def _extract_rule_ids(reasons: object) -> set[str]:
    extracted: set[str] = set()
    if not isinstance(reasons, (list, tuple)):
        return extracted
    for reason in reasons:
        rule_id = getattr(reason, "rule_id", None)
        if isinstance(rule_id, str) and rule_id:
            extracted.add(rule_id)
            continue
        if isinstance(reason, str) and reason:
            extracted.add(reason)
    return extracted


def _report_fixture() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = 32
    timestamps = pd.date_range("2024-01-01", periods=rows, freq="h", tz="UTC")
    close = pd.Series([100.0] * rows)
    ohlcv = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
        }
    )
    features = pd.DataFrame({"atr_14": [0.5] * rows})
    return features, ohlcv


def test_s4_deny_paths_emit_catalog_rule_ids() -> None:
    cfg = RiskConfig(
        missing_red=0.2,
        atr_yellow=0.02,
        atr_red=0.05,
        rvol_yellow=0.02,
        rvol_red=0.05,
    )

    red_decision = evaluate_risk(_inputs(invalid_index=True), cfg)
    rule_ids = _extract_rule_ids(red_decision.reasons)
    assert rule_ids
    assert rule_ids.issubset(ALL_RULE_IDS)

    invalid_decision, _invalid_audit = risk_veto({"symbol": "BTCUSDT"}, cfg)
    invalid_rule_ids = _extract_rule_ids(invalid_decision.reasons)
    assert invalid_rule_ids
    assert invalid_rule_ids.issubset(ALL_RULE_IDS)
    assert RiskRuleId.RISK_INPUTS_INVALID.value in invalid_rule_ids

    missing_policy_decision, _missing_policy_audit = risk_veto(
        _inputs().to_dict(),
        None,  # type: ignore[arg-type]
    )
    missing_policy_rule_ids = _extract_rule_ids(missing_policy_decision.reasons)
    assert missing_policy_rule_ids
    assert missing_policy_rule_ids.issubset(ALL_RULE_IDS)
    assert RiskRuleId.RISK_POLICY_MISSING.value in missing_policy_rule_ids


def test_s4_pack_fields_non_empty_on_decisions_and_artifacts() -> None:
    cfg = L3_BALANCED
    decision = evaluate_risk(_inputs(), cfg)
    assert decision.pack_id == cfg.pack_id
    assert decision.pack_version == cfg.pack_version
    assert decision.pack_id
    assert decision.pack_version

    features, ohlcv = _report_fixture()
    report = evaluate_risk_report(features, ohlcv, config=cfg)
    report_config = report.get("config")
    assert isinstance(report_config, dict)
    assert isinstance(report_config.get("pack_id"), str) and report_config["pack_id"]
    assert isinstance(report_config.get("pack_version"), str) and report_config["pack_version"]
    assert report_config["pack_id"] == cfg.pack_id
    assert report_config["pack_version"] == cfg.pack_version


def test_s4_core_pack_presets_have_stable_non_empty_ids() -> None:
    packs = (L1_CONSERVATIVE, L3_BALANCED, L5_AGGRESSIVE)
    ids = [pack.pack_id for pack in packs]
    assert len(ids) == len(set(ids))
    assert all(isinstance(pack.pack_version, str) and pack.pack_version for pack in packs)
    assert all(isinstance(pack.config_version, str) and pack.config_version for pack in packs)
