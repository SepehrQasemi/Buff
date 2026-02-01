"""Evaluator determinism tests for regime semantics."""

from __future__ import annotations

from pathlib import Path

from buff.regimes.evaluator import evaluate_regime
from buff.regimes.parser import load_regime_config


def _write_yaml(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "regimes.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_evaluator_is_deterministic(tmp_path: Path) -> None:
    payload = """
    schema_version: "1"
    regimes:
      - regime_id: RISK_OFF
        description: x
        priority: 3
        conditions:
          any:
            - gte: { atr_pct: 0.5 }
        allowed_strategy_families: [do_not_trade]
        forbidden_strategy_families: [trend_following]
      - regime_id: FIRST
        description: x
        priority: 2
        conditions:
          any:
            - gte: { atr_pct: 0.1 }
        allowed_strategy_families: [trend_following]
        forbidden_strategy_families: [do_not_trade]
      - regime_id: SECOND
        description: x
        priority: 1
        conditions:
          any:
            - gte: { atr_pct: 0.1 }
        allowed_strategy_families: [breakout]
        forbidden_strategy_families: [do_not_trade]
      - regime_id: NEUTRAL
        description: x
        priority: 0
        allowed_strategy_families: [trend_following]
        forbidden_strategy_families: [do_not_trade]
    """
    path = _write_yaml(tmp_path, payload)
    config = load_regime_config(path)
    features = {"atr_pct": 0.2}
    decision_a = evaluate_regime(features, config)
    decision_b = evaluate_regime(features, config)
    assert decision_a == decision_b


def test_first_match_wins_by_priority(tmp_path: Path) -> None:
    payload = """
    schema_version: "1"
    regimes:
      - regime_id: RISK_OFF
        description: x
        priority: 3
        conditions:
          any:
            - gte: { atr_pct: 0.5 }
        allowed_strategy_families: [do_not_trade]
        forbidden_strategy_families: [trend_following]
      - regime_id: FIRST
        description: x
        priority: 2
        conditions:
          any:
            - gte: { atr_pct: 0.1 }
        allowed_strategy_families: [trend_following]
        forbidden_strategy_families: [do_not_trade]
      - regime_id: SECOND
        description: x
        priority: 1
        conditions:
          any:
            - gte: { atr_pct: 0.1 }
        allowed_strategy_families: [breakout]
        forbidden_strategy_families: [do_not_trade]
      - regime_id: NEUTRAL
        description: x
        priority: 0
        allowed_strategy_families: [trend_following]
        forbidden_strategy_families: [do_not_trade]
    """
    path = _write_yaml(tmp_path, payload)
    config = load_regime_config(path)
    decision = evaluate_regime({"atr_pct": 0.2}, config)
    assert decision.regime_id == "FIRST"
