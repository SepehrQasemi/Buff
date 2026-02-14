from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.plugins.registry import (
    get_validation_summary_from_artifacts,
    list_invalid_indicators,
    list_invalid_strategies,
    list_valid_indicators,
    list_valid_strategies,
)

_FALLBACK_STRATEGIES = [
    {
        "id": "hold",
        "name": "Hold (baseline)",
        "version": "1.0.0",
        "category": "core",
        "schema": {
            "id": "hold",
            "name": "Hold (baseline)",
            "version": "1.0.0",
            "description": "Enter once at the start and exit at the end.",
            "category": "core",
            "warmup_bars": 0,
            "params": [],
            "inputs": [],
            "outputs": [],
        },
    },
    {
        "id": "ma_cross",
        "name": "MA Cross",
        "version": "1.0.0",
        "category": "core",
        "schema": {
            "id": "ma_cross",
            "name": "MA Cross",
            "version": "1.0.0",
            "description": "Simple moving average crossover.",
            "category": "core",
            "warmup_bars": 20,
            "params": [
                {
                    "name": "fast_period",
                    "type": "int",
                    "default": 10,
                    "min": 1,
                    "description": "Fast moving average window.",
                },
                {
                    "name": "slow_period",
                    "type": "int",
                    "default": 20,
                    "min": 2,
                    "description": "Slow moving average window.",
                },
            ],
            "inputs": ["close"],
            "outputs": [],
        },
    },
    {
        "id": "demo_threshold",
        "name": "Demo Threshold",
        "version": "1.0.0",
        "category": "core",
        "schema": {
            "id": "demo_threshold",
            "name": "Demo Threshold",
            "version": "1.0.0",
            "description": "Hold-like strategy with a threshold parameter.",
            "category": "core",
            "warmup_bars": 0,
            "params": [
                {
                    "name": "threshold",
                    "type": "float",
                    "default": 0.0,
                    "min": 0.0,
                    "max": 10.0,
                    "description": "Threshold parameter for demo strategy.",
                }
            ],
            "inputs": ["close"],
            "outputs": [],
        },
    },
]


def _fallback_enabled() -> bool:
    if os.getenv("DEMO_MODE", "").strip().lower() in {"1", "true", "yes", "on"}:
        return False
    return bool(os.getenv("RUNS_ROOT", "").strip())


def list_active_plugins(artifacts_root: Path) -> dict[str, list[dict[str, Any]]]:
    indicators = list_valid_indicators(artifacts_root)
    strategies = list_valid_strategies(artifacts_root)
    if not strategies and _fallback_enabled():
        strategies = [dict(item) for item in _FALLBACK_STRATEGIES]
    return {"indicators": indicators, "strategies": strategies}


def list_failed_plugins(artifacts_root: Path) -> dict[str, list[dict[str, Any]]]:
    return {
        "indicators": list_invalid_indicators(artifacts_root),
        "strategies": list_invalid_strategies(artifacts_root),
    }


def get_validation_summary(artifacts_root: Path) -> dict[str, Any]:
    return get_validation_summary_from_artifacts(artifacts_root)
