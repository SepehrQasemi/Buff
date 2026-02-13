from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

from src.plugins.discovery import discover_plugins
from src.plugins.validation import validate_candidate


@dataclass
class DemoContext:
    series: dict
    params: dict
    indicators: dict
    bar_index: int | None
    warmup_bars: int | None


def _find_candidate(repo_root: Path, plugin_type: str, plugin_id: str):
    candidates = discover_plugins(repo_root)
    for candidate in candidates:
        if candidate.plugin_type == plugin_type and candidate.plugin_id == plugin_id:
            return candidate
    raise AssertionError(f"plugin not found: {plugin_type}/{plugin_id}")


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"failed to load module {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_demo_plugins_validate() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    indicator = _find_candidate(repo_root, "indicator", "demo_sma")
    strategy = _find_candidate(repo_root, "strategy", "demo_threshold")

    indicator_result = validate_candidate(indicator)
    strategy_result = validate_candidate(strategy)

    assert indicator_result.status == "VALID", indicator_result.reason_codes
    assert strategy_result.status == "VALID", strategy_result.reason_codes


def test_demo_plugins_deterministic_and_causal() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    indicator_path = repo_root / "user_indicators" / "demo_sma" / "indicator.py"
    strategy_path = repo_root / "user_strategies" / "demo_threshold" / "strategy.py"

    indicator_mod = _load_module(indicator_path, "demo_sma")
    strategy_mod = _load_module(strategy_path, "demo_threshold")

    close = [100.0, 100.5, 101.0, 100.8, 101.2, 101.6, 101.1]
    warmup = 5
    indicator_params = {"period": 3}
    strategy_params = {"threshold": 0.0}
    full_close = tuple(close)

    sma_values: list[float] = []
    for bar in range(len(close)):
        ctx_full = DemoContext(
            series={"close": full_close},
            params=indicator_params,
            indicators={},
            bar_index=bar,
            warmup_bars=warmup,
        )
        out_a = indicator_mod.compute(ctx_full)
        out_b = indicator_mod.compute(ctx_full)
        assert out_a == out_b

        ctx_prefix = DemoContext(
            series={"close": tuple(close[: bar + 1])},
            params=indicator_params,
            indicators={},
            bar_index=bar,
            warmup_bars=warmup,
        )
        out_prefix = indicator_mod.compute(ctx_prefix)
        assert out_a == out_prefix
        sma_values.append(float(out_a["sma"]))

    full_indicators = {"demo_sma": {"sma": tuple(sma_values)}}

    for bar in range(len(close)):
        ctx_full = DemoContext(
            series={"close": full_close},
            params=strategy_params,
            indicators=full_indicators,
            bar_index=bar,
            warmup_bars=warmup,
        )
        out_a = strategy_mod.on_bar(ctx_full)
        out_b = strategy_mod.on_bar(ctx_full)
        assert out_a == out_b

        ctx_prefix = DemoContext(
            series={"close": tuple(close[: bar + 1])},
            params=strategy_params,
            indicators={"demo_sma": {"sma": tuple(sma_values[: bar + 1])}},
            bar_index=bar,
            warmup_bars=warmup,
        )
        out_prefix = strategy_mod.on_bar(ctx_prefix)
        assert out_a == out_prefix

        if bar < warmup:
            assert out_a.get("intent") == "HOLD"
