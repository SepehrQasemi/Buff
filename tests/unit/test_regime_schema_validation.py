"""Schema validation tests for regime semantics."""

from __future__ import annotations

from pathlib import Path

import pytest

from buff.regimes.evaluator import evaluate_regime
from buff.regimes.errors import RegimeSchemaError
from buff.regimes.parser import load_regime_config


def _write_yaml(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "regimes.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_unknown_feature_rejected(tmp_path: Path) -> None:
    payload = """
    schema_version: "1"
    regimes:
      - regime_id: RISK_OFF
        description: x
        priority: 2
        conditions:
          any:
            - gte: { unknown_feature: 1.0 }
        allowed_strategy_families: [do_not_trade]
        forbidden_strategy_families: [trend_following]
      - regime_id: NEUTRAL
        description: x
        priority: 0
        allowed_strategy_families: [trend_following]
        forbidden_strategy_families: [do_not_trade]
    """
    path = _write_yaml(tmp_path, payload)
    with pytest.raises(RegimeSchemaError):
        load_regime_config(path)


def test_missing_priority_rejected(tmp_path: Path) -> None:
    payload = """
    schema_version: "1"
    regimes:
      - regime_id: RISK_OFF
        description: x
        conditions:
          any:
            - gte: { atr_pct: 0.02 }
        allowed_strategy_families: [do_not_trade]
        forbidden_strategy_families: [trend_following]
      - regime_id: NEUTRAL
        description: x
        priority: 0
        allowed_strategy_families: [trend_following]
        forbidden_strategy_families: [do_not_trade]
    """
    path = _write_yaml(tmp_path, payload)
    with pytest.raises(RegimeSchemaError):
        load_regime_config(path)


def test_neutral_must_be_lowest_priority(tmp_path: Path) -> None:
    payload = """
    schema_version: "1"
    regimes:
      - regime_id: RISK_OFF
        description: x
        priority: 3
        conditions:
          any:
            - gte: { atr_pct: 0.02 }
        allowed_strategy_families: [do_not_trade]
        forbidden_strategy_families: [trend_following]
      - regime_id: NEUTRAL
        description: x
        priority: 1
        allowed_strategy_families: [trend_following]
        forbidden_strategy_families: [do_not_trade]
      - regime_id: OTHER
        description: x
        priority: 0
        conditions:
          any:
            - gte: { atr_pct: 0.01 }
        allowed_strategy_families: [trend_following]
        forbidden_strategy_families: [do_not_trade]
    """
    path = _write_yaml(tmp_path, payload)
    with pytest.raises(RegimeSchemaError):
        load_regime_config(path)


def test_missing_features_fail_closed() -> None:
    config = load_regime_config(Path("knowledge/regimes.yaml"))
    decision = evaluate_regime({"atr_pct": 0.005}, config)
    assert decision.regime_id == "RISK_OFF"
    assert "missing_features" in decision.matched_conditions_summary
