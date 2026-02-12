from __future__ import annotations

from pathlib import Path

import pytest

from src.plugins.discovery import discover_plugins
from src.plugins import validation as validation_module
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
    description: "Lookback period"
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
    description: "Entry threshold"
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

    assert indicator_result.status == "VALID"
    assert indicator_result.reason_codes == []
    assert strategy_result.status == "VALID"
    assert strategy_result.reason_codes == []


def test_validation_repeated_runs_are_consistent(tmp_path: Path) -> None:
    _write(tmp_path / "user_indicators/simple_rsi/indicator.yaml", VALID_INDICATOR_YAML)
    _write(tmp_path / "user_indicators/simple_rsi/indicator.py", VALID_INDICATOR_PY)
    candidate = _candidate(tmp_path, "indicator", "simple_rsi")

    first = validate_candidate(candidate)
    second = validate_candidate(candidate)

    assert first.status == second.status
    assert first.reason_codes == second.reason_codes


def test_schema_validation_fails_for_missing_fields(tmp_path: Path) -> None:
    bad_indicator_yaml = VALID_INDICATOR_YAML.replace("version: 1.0.0\n", "")
    _write(tmp_path / "user_indicators/bad/indicator.yaml", bad_indicator_yaml)
    _write(tmp_path / "user_indicators/bad/indicator.py", VALID_INDICATOR_PY)
    bad_candidate = _candidate(tmp_path, "indicator", "bad")

    result = validate_candidate(bad_candidate)
    assert result.status == "INVALID"
    assert any(code.startswith("SCHEMA_MISSING_FIELD:") for code in result.reason_codes)


def test_schema_validation_fails_for_strategy_missing_outputs(tmp_path: Path) -> None:
    bad_strategy_yaml = VALID_STRATEGY_YAML.replace(STRATEGY_OUTPUTS_BLOCK, "")
    _write(tmp_path / "user_strategies/bad/strategy.yaml", bad_strategy_yaml)
    _write(tmp_path / "user_strategies/bad/strategy.py", VALID_STRATEGY_PY)
    bad_candidate = _candidate(tmp_path, "strategy", "bad")

    result = validate_candidate(bad_candidate)
    assert result.status == "INVALID"
    assert any(code.startswith("SCHEMA_MISSING_FIELD:") for code in result.reason_codes)


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
    assert result.status == "INVALID"
    assert any(code.startswith("FORBIDDEN_IMPORT:") for code in result.reason_codes)


@pytest.mark.parametrize("attr", ["now", "utcnow", "today"])
def test_static_safety_catches_datetime_variants(tmp_path: Path, attr: str) -> None:
    unsafe_py = f"""\
from datetime import datetime


def get_schema():
    return {{}}


def compute(ctx):
    datetime.{attr}()
    return {{"rsi": 50.0}}
"""
    plugin_id = f"unsafe_datetime_{attr}"
    _write(
        tmp_path / f"user_indicators/{plugin_id}/indicator.yaml",
        VALID_INDICATOR_YAML.replace("simple_rsi", plugin_id),
    )
    _write(tmp_path / f"user_indicators/{plugin_id}/indicator.py", unsafe_py)
    bad_candidate = _candidate(tmp_path, "indicator", plugin_id)

    result = validate_candidate(bad_candidate)
    assert result.status == "INVALID"
    assert any(
        code.startswith("FORBIDDEN_IMPORT:") or code.startswith("NON_DETERMINISTIC_API:")
        for code in result.reason_codes
    )


def test_fail_closed_on_validator_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path / "user_indicators/simple_rsi/indicator.yaml", VALID_INDICATOR_YAML)
    _write(tmp_path / "user_indicators/simple_rsi/indicator.py", VALID_INDICATOR_PY)
    candidate = _candidate(tmp_path, "indicator", "simple_rsi")

    def boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr("src.plugins.validation._load_yaml", boom)
    result = validate_candidate(candidate)
    assert result.status == "INVALID"
    assert "VALIDATION_EXCEPTION" in result.reason_codes


def test_missing_required_files_is_invalid(tmp_path: Path) -> None:
    _write(
        tmp_path / "user_indicators/missing/indicator.yaml",
        VALID_INDICATOR_YAML.replace("simple_rsi", "missing"),
    )
    candidate = _candidate(tmp_path, "indicator", "missing")

    result = validate_candidate(candidate)
    assert result.status == "INVALID"
    assert any(code.startswith("MISSING_FILE:") for code in result.reason_codes)


def test_strategy_invalid_intent_is_detected(tmp_path: Path) -> None:
    bad_yaml = VALID_STRATEGY_YAML.replace("simple_cross", "bad_intent")
    bad_py = """\
def get_schema():
    return {}


def on_bar(ctx):
    return {"intent": "FLY"}
"""
    _write(tmp_path / "user_strategies/bad_intent/strategy.yaml", bad_yaml)
    _write(tmp_path / "user_strategies/bad_intent/strategy.py", bad_py)
    candidate = _candidate(tmp_path, "strategy", "bad_intent")

    result = validate_candidate(candidate)
    assert result.status == "INVALID"
    assert "INTENT_INVALID" in result.reason_codes


def test_strategy_nan_after_warmup_is_invalid(tmp_path: Path) -> None:
    bad_yaml = VALID_STRATEGY_YAML.replace(
        "provides_confidence: false", "provides_confidence: true"
    ).replace("simple_cross", "nan_confidence")
    bad_yaml = bad_yaml.replace("warmup_bars: 20", "warmup_bars: 1")
    bad_py = """\
def get_schema():
    return {}


def on_bar(ctx):
    return {"intent": "HOLD", "confidence": float("nan")}
"""
    _write(tmp_path / "user_strategies/nan_confidence/strategy.yaml", bad_yaml)
    _write(tmp_path / "user_strategies/nan_confidence/strategy.py", bad_py)
    candidate = _candidate(tmp_path, "strategy", "nan_confidence")

    result = validate_candidate(candidate)
    assert result.status == "INVALID"
    assert "NAN_POLICY_VIOLATION" in result.reason_codes


def test_strategy_confidence_none_is_invalid(tmp_path: Path) -> None:
    bad_yaml = (
        VALID_STRATEGY_YAML.replace("simple_cross", "none_confidence")
        .replace("provides_confidence: false", "provides_confidence: true")
        .replace("warmup_bars: 20", "warmup_bars: 0")
    )
    bad_py = """\
def get_schema():
    return {}


def on_bar(ctx):
    return {"intent": "HOLD", "confidence": None}
"""
    _write(tmp_path / "user_strategies/none_confidence/strategy.yaml", bad_yaml)
    _write(tmp_path / "user_strategies/none_confidence/strategy.py", bad_py)
    candidate = _candidate(tmp_path, "strategy", "none_confidence")

    result = validate_candidate(candidate)
    assert result.status == "INVALID"
    assert "CONFIDENCE_MISSING" in result.reason_codes


def test_indicator_nondeterminism_is_invalid(tmp_path: Path) -> None:
    bad_yaml = VALID_INDICATOR_YAML.replace("simple_rsi", "nondet")
    bad_py = """\
def get_schema():
    return {}


def compute(ctx, counter=iter([1, 2, 3])):
    return {"rsi": next(counter)}
"""
    _write(tmp_path / "user_indicators/nondet/indicator.yaml", bad_yaml)
    _write(tmp_path / "user_indicators/nondet/indicator.py", bad_py)
    candidate = _candidate(tmp_path, "indicator", "nondet")

    result = validate_candidate(candidate)
    assert result.status == "INVALID"
    assert "NON_DETERMINISTIC_OUTPUT" in result.reason_codes


def test_indicator_none_after_warmup_is_invalid_type(tmp_path: Path) -> None:
    bad_yaml = VALID_INDICATOR_YAML.replace("simple_rsi", "none_output").replace(
        "warmup_bars: 14", "warmup_bars: 0"
    )
    bad_py = """\
def get_schema():
    return {}


def compute(ctx):
    return {"rsi": None}
"""
    _write(tmp_path / "user_indicators/none_output/indicator.yaml", bad_yaml)
    _write(tmp_path / "user_indicators/none_output/indicator.py", bad_py)
    candidate = _candidate(tmp_path, "indicator", "none_output")

    result = validate_candidate(candidate)
    assert result.status == "INVALID"
    assert "OUTPUT_INVALID_TYPE" in result.reason_codes


def test_indicator_nan_after_warmup_is_policy_violation(tmp_path: Path) -> None:
    bad_yaml = VALID_INDICATOR_YAML.replace("simple_rsi", "nan_output").replace(
        "warmup_bars: 14", "warmup_bars: 0"
    )
    bad_py = """\
def get_schema():
    return {}


def compute(ctx):
    return {"rsi": float("nan")}
"""
    _write(tmp_path / "user_indicators/nan_output/indicator.yaml", bad_yaml)
    _write(tmp_path / "user_indicators/nan_output/indicator.py", bad_py)
    candidate = _candidate(tmp_path, "indicator", "nan_output")

    result = validate_candidate(candidate)
    assert result.status == "INVALID"
    assert "NAN_POLICY_VIOLATION" in result.reason_codes


def test_indicator_series_mutation_is_invalid(tmp_path: Path) -> None:
    bad_yaml = VALID_INDICATOR_YAML.replace("simple_rsi", "mutate_series")
    bad_py = """\
def get_schema():
    return {}


def compute(ctx):
    ctx.series["close"][0] = 1.0
    return {"rsi": 50.0}
"""
    _write(tmp_path / "user_indicators/mutate_series/indicator.yaml", bad_yaml)
    _write(tmp_path / "user_indicators/mutate_series/indicator.py", bad_py)
    candidate = _candidate(tmp_path, "indicator", "mutate_series")

    result = validate_candidate(candidate)
    assert result.status == "INVALID"
    assert "RUNTIME_ERROR" in result.reason_codes


def test_strategy_indicator_ids_validation(tmp_path: Path) -> None:
    indicator_yaml = VALID_INDICATOR_YAML.replace("simple_rsi", "rsi_fast")
    _write(tmp_path / "user_indicators/rsi_fast/indicator.yaml", indicator_yaml)

    good_yaml = VALID_STRATEGY_YAML.replace("simple_cross", "uses_indicator").replace(
        "indicators: []", "indicators: [rsi_fast]"
    )
    _write(tmp_path / "user_strategies/uses_indicator/strategy.yaml", good_yaml)
    _write(tmp_path / "user_strategies/uses_indicator/strategy.py", VALID_STRATEGY_PY)
    candidate = _candidate(tmp_path, "strategy", "uses_indicator")

    result = validate_candidate(candidate)
    assert result.status == "VALID"


def test_strategy_indicator_ids_invalid(tmp_path: Path) -> None:
    bad_yaml = VALID_STRATEGY_YAML.replace("simple_cross", "bad_indicator_id").replace(
        "indicators: []", "indicators: [Bad-ID]"
    )
    _write(tmp_path / "user_strategies/bad_indicator_id/strategy.yaml", bad_yaml)
    _write(tmp_path / "user_strategies/bad_indicator_id/strategy.py", VALID_STRATEGY_PY)
    candidate = _candidate(tmp_path, "strategy", "bad_indicator_id")

    result = validate_candidate(candidate)
    assert result.status == "INVALID"
    assert any(code.startswith("INVALID_ENUM:inputs.indicators") for code in result.reason_codes)


def test_runtime_worker_exitcode_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path / "user_indicators/simple_rsi/indicator.yaml", VALID_INDICATOR_YAML)
    _write(tmp_path / "user_indicators/simple_rsi/indicator.py", VALID_INDICATOR_PY)
    candidate = _candidate(tmp_path, "indicator", "simple_rsi")

    monkeypatch.setattr(
        validation_module,
        "_runtime_worker",
        validation_module._runtime_worker_crash_for_test,
    )

    result = validate_candidate(candidate)
    assert result.status == "INVALID"
    assert "RUNTIME_ERROR" in result.reason_codes
    assert any("exitcode=137" in message for message in result.reason_messages)


def test_runtime_timeout_is_invalid(tmp_path: Path) -> None:
    bad_yaml = VALID_INDICATOR_YAML.replace("simple_rsi", "timeout_indicator")
    bad_py = """\
def get_schema():
    return {}


def compute(ctx):
    while True:
        pass
"""
    _write(tmp_path / "user_indicators/timeout_indicator/indicator.yaml", bad_yaml)
    _write(tmp_path / "user_indicators/timeout_indicator/indicator.py", bad_py)
    candidate = _candidate(tmp_path, "indicator", "timeout_indicator")

    result = validate_candidate(candidate)
    assert result.status == "INVALID"
    assert "RUNTIME_TIMEOUT" in result.reason_codes


def test_strategy_infinite_loop_times_out(tmp_path: Path) -> None:
    bad_yaml = VALID_STRATEGY_YAML.replace("simple_cross", "timeout_strategy").replace(
        "warmup_bars: 20", "warmup_bars: 0"
    )
    bad_py = """\
def get_schema():
    return {}


def on_bar(ctx):
    while True:
        pass
"""
    _write(tmp_path / "user_strategies/timeout_strategy/strategy.yaml", bad_yaml)
    _write(tmp_path / "user_strategies/timeout_strategy/strategy.py", bad_py)
    candidate = _candidate(tmp_path, "strategy", "timeout_strategy")

    result = validate_candidate(candidate)
    assert result.status == "INVALID"
    assert "RUNTIME_TIMEOUT" in result.reason_codes
