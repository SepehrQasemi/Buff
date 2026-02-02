"""Feature runner for deterministic feature computation."""

from __future__ import annotations

import pandas as pd

from buff.features.contract import build_feature_specs_from_registry
from buff.features.registry import FEATURES
from buff.features.runner_pure import run_features_pure


def run_features(df: pd.DataFrame, mode: str = "train") -> pd.DataFrame:
    if mode not in {"train", "live"}:
        raise ValueError("mode must be 'train' or 'live'")

    specs = build_feature_specs_from_registry(FEATURES)
    out, _ = run_features_pure(df, specs, validate_contract=True)
    return out
