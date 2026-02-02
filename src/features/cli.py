"""Standalone CLI for M3 feature/regime artifact generation."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import pandas as pd

from .build_features import FEATURE_COLUMNS, build_features
from .regime import REGIME_COLUMNS, build_market_state, write_market_state


def _coerce_output(frame: pd.DataFrame) -> pd.DataFrame:
    ordered = FEATURE_COLUMNS + REGIME_COLUMNS
    if "volatility_cluster" in frame.columns:
        ordered.append("volatility_cluster")
    missing = [col for col in ordered if col not in frame.columns]
    if missing:
        raise ValueError(f"Missing expected output columns: {missing}")

    out = frame[ordered].copy()
    for col in FEATURE_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce").astype("float64")
    for col in REGIME_COLUMNS:
        out[col] = out[col].astype("string")
    if "volatility_cluster" in out.columns:
        out["volatility_cluster"] = out["volatility_cluster"].astype("string")
    return out


def _parse_args(argv: Iterable[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build deterministic market_state features.")
    parser.add_argument("--input", dest="input_path", required=True, help="OHLCV parquet input.")
    parser.add_argument(
        "--output",
        dest="output_path",
        default="features/market_state.parquet",
        help="Output parquet path.",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    input_path = Path(args.input_path)
    output_path = Path(args.output_path)

    ohlcv = pd.read_parquet(input_path)
    features = build_features(ohlcv)
    market_state = build_market_state(features)
    market_state = _coerce_output(market_state)

    write_market_state(market_state, out_path=output_path)
    return 0


if __name__ == "__main__":
    main()
