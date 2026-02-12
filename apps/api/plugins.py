from __future__ import annotations

from pathlib import Path
from typing import Any

from src.plugins.registry import (
    get_validation_summary_from_artifacts,
    list_invalid_indicators,
    list_invalid_strategies,
    list_valid_indicators,
    list_valid_strategies,
)


def list_active_plugins(artifacts_root: Path) -> dict[str, list[dict[str, Any]]]:
    return {
        "indicators": list_valid_indicators(artifacts_root),
        "strategies": list_valid_strategies(artifacts_root),
    }


def list_failed_plugins(artifacts_root: Path) -> dict[str, list[dict[str, Any]]]:
    return {
        "indicators": list_invalid_indicators(artifacts_root),
        "strategies": list_invalid_strategies(artifacts_root),
    }


def get_validation_summary(artifacts_root: Path) -> dict[str, Any]:
    return get_validation_summary_from_artifacts(artifacts_root)
