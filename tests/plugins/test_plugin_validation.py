from __future__ import annotations

from pathlib import Path

import pytest

from src.plugins.discovery import discover_plugins
from src.plugins.validation import validate_candidate

VALID_INDICATOR_YAML = """\
id: simple_rsi
name: Simple RSI
version: 1.0.0
category: momentum
inputs: [close]
outputs: [rsi]
params:
  - name: period
    type: int
    default: 14
    min: 2
    max: 200
    step: 1
warmup_bars: 14
nan_policy: propagate
"""

VALID_INDICATOR_PY = """\
def get_schema():
    return {}


def compute(ctx):
    return {"rsi": 50.0}
"""

VALID_STRATEGY_YAML = """\
id: simple_cross
name: Simple Cross
version: 1.0.0
category: trend
warmup_bars: 20
inputs:
  series: [close]
  indicators: []
params:
  - name: threshold
    type: float
    default: 0.0
    min: -1.0
    max: 1.0
    step: 0.1
outputs:
  intents: [HOLD, ENTER_LONG, EXIT_LONG]
  provides_confidence: false
"""

VALID_STRATEGY_PY = """\
def get_schema():
    return {}


def on_bar(ctx):
    return {"intent": "HOLD"}
"""

STRATEGY_OUTPUTS_BLOCK = """\
outputs:
  intents: [HOLD, ENTER_LONG, EXIT_LONG]
  provides_confidence: false
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _candidate(root: Path, plugin_type: str, plugin_id: str) -> object:
    candidates = discover_plugins(root)
    for candidate in candidates:
        if candidate.plugin_type == plugin_type and candidate.plugin_id == plugin_id:
            return candidate
    raise AssertionError(f"candidate not found: {plugin_type}/{plugin_id}")


def test_discovery_finds_candidates(tmp_path: Path) -> None:
    _write(tmp_path / "user_indicators/simple_rsi/indicator.yaml", VALID_INDICATOR_YAML)
    _write(tmp_path / "user_indicators/simple_rsi/indicator.py", VALID_INDICATOR_PY)
    _write(tmp_path / "user_strategies/simple_cross/strategy.yaml", VALID_STRATEGY_YAML)
    _write(tmp_path / "user_strategies/simple_cross/strategy.py", VALID_STRATEGY_PY)

    candidates = discover_plugins(tmp_path)
    ids = sorted((candidate.plugin_type, candidate.plugin_id) for candidate in candidates)
    assert ids == [("indicator", "simple_rsi"), ("strategy", "simple_cross")]


def test_validation_passes_for_valid_plugins(tmp_path: Path) -> None:
    _write(tmp_path / "user_indicators/simple_rsi/indicator.yaml", VALID_INDICATOR_YAML)
    _write(tmp_path / "user_indicators/simple_rsi/indicator.py", VALID_INDICATOR_PY)
    _write(tmp_path / "user_strategies/simple_cross/strategy.yaml", VALID_STRATEGY_YAML)
    _write(tmp_path / "user_strategies/simple_cross/strategy.py", VALID_STRATEGY_PY)

    indicator = _candidate(tmp_path, "indicator", "simple_rsi")
    strategy = _candidate(tmp_path, "strategy", "simple_cross")

    indicator_result = validate_candidate(indicator)
    strategy_result = validate_candidate(strategy)

    assert indicator_result.status == "PASS"
    assert indicator_result.errors == []
    assert strategy_result.status == "PASS"
    assert strategy_result.errors == []


def test_schema_validation_fails_for_missing_fields(tmp_path: Path) -> None:
    bad_indicator_yaml = VALID_INDICATOR_YAML.replace("version: 1.0.0\n", "")
    _write(tmp_path / "user_indicators/bad/indicator.yaml", bad_indicator_yaml)
    _write(tmp_path / "user_indicators/bad/indicator.py", VALID_INDICATOR_PY)
    bad_candidate = _candidate(tmp_path, "indicator", "bad")

    result = validate_candidate(bad_candidate)
    assert result.status == "FAIL"
    assert any(error.rule_id == "SCHEMA_MISSING_FIELD" for error in result.errors)


def test_schema_validation_fails_for_strategy_missing_outputs(tmp_path: Path) -> None:
    bad_strategy_yaml = VALID_STRATEGY_YAML.replace(STRATEGY_OUTPUTS_BLOCK, "")
    _write(tmp_path / "user_strategies/bad/strategy.yaml", bad_strategy_yaml)
    _write(tmp_path / "user_strategies/bad/strategy.py", VALID_STRATEGY_PY)
    bad_candidate = _candidate(tmp_path, "strategy", "bad")

    result = validate_candidate(bad_candidate)
    assert result.status == "FAIL"
    assert any(error.rule_id == "SCHEMA_MISSING_FIELD" for error in result.errors)


def test_static_safety_catches_forbidden_imports(tmp_path: Path) -> None:
    unsafe_py = """\
import os


def get_schema():
    return {}


def compute(ctx):
    return {"rsi": 50.0}
"""
    _write(
        tmp_path / "user_indicators/unsafe/indicator.yaml",
        VALID_INDICATOR_YAML.replace("simple_rsi", "unsafe"),
    )
    _write(tmp_path / "user_indicators/unsafe/indicator.py", unsafe_py)
    bad_candidate = _candidate(tmp_path, "indicator", "unsafe")

    result = validate_candidate(bad_candidate)
    assert result.status == "FAIL"
    assert any(error.rule_id == "FORBIDDEN_IMPORT" for error in result.errors)


def test_fail_closed_on_validator_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path / "user_indicators/simple_rsi/indicator.yaml", VALID_INDICATOR_YAML)
    _write(tmp_path / "user_indicators/simple_rsi/indicator.py", VALID_INDICATOR_PY)
    candidate = _candidate(tmp_path, "indicator", "simple_rsi")

    def boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr("src.plugins.validation._load_yaml", boom)
    result = validate_candidate(candidate)
    assert result.status == "FAIL"
    assert any(error.rule_id == "VALIDATOR_CRASH" for error in result.errors)
