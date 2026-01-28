"""CLI entrypoint for feature generation."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from buff.features.runner import run_features


def _read_input(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Input not found: {path}")
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path, engine="pyarrow")
    raise ValueError("Input must be .csv or .parquet")


def main() -> None:
    if len(sys.argv) != 4 or sys.argv[1] != "features":
        print("Usage: buff features <input_path> <output_path>")
        raise SystemExit(2)

    input_path = Path(sys.argv[2])
    output_path = Path(sys.argv[3])

    df = _read_input(input_path)
    out = run_features(df)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(output_path, engine="pyarrow")


if __name__ == "__main__":
    main()
