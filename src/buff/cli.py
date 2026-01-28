"""CLI entrypoint for feature generation."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from buff.features.metadata import build_metadata, sha256_file, write_json
from buff.features.registry import FEATURES
from buff.features.runner import run_features
from risk.evaluator import evaluate_risk
from risk.report import write_risk_report
from risk.types import RiskContext


def _detect_input_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".parquet":
        return "parquet"
    raise ValueError("Input must be .csv or .parquet")


def _read_input(path: Path, input_format: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Input not found: {path}")
    if input_format == "csv":
        return pd.read_csv(path)
    if input_format == "parquet":
        return pd.read_parquet(path, engine="pyarrow")
    raise ValueError("Input format must be csv or parquet")


def _normalize_timestamp_column(df: pd.DataFrame) -> pd.DataFrame:
    if "timestamp" in df.columns:
        return df
    if "ts" in df.columns:
        out = df.copy()
        out["timestamp"] = out["ts"]
        return out
    return df


def main() -> None:
    parser = argparse.ArgumentParser(prog="buff")
    subparsers = parser.add_subparsers(dest="command", required=True)

    features_parser = subparsers.add_parser("features", help="Generate features")
    features_parser.add_argument("input_path")
    features_parser.add_argument("output_path")
    features_parser.add_argument("--meta", dest="meta_path")
    features_parser.add_argument("--symbol", type=str, default=None, help="Symbol label")
    features_parser.add_argument("--timeframe", type=str, default=None, help="Timeframe label")
    features_parser.add_argument("--run_id", type=str, default=None, help="Optional run id")

    args = parser.parse_args()
    if args.command != "features":
        raise SystemExit(2)

    input_path = Path(args.input_path)
    output_path = Path(args.output_path)
    meta_path = Path(args.meta_path) if args.meta_path else Path(f"{output_path}.meta.json")

    input_format = _detect_input_format(input_path)
    input_sha256 = sha256_file(input_path)
    df = _read_input(input_path, input_format)
    feature_input = _normalize_timestamp_column(df)

    out = run_features(feature_input)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(output_path, engine="pyarrow")

    output_sha256 = sha256_file(output_path)
    feature_params = {}
    for name, spec in FEATURES.items():
        params = dict(spec["params"])
        kind = spec["kind"]
        if kind in {"ema", "sma", "std", "bbands"}:
            params["_valid_from"] = params["period"] - 1
        elif kind in {"rsi", "atr"}:
            params["_valid_from"] = params["period"]
        elif kind == "macd":
            params["_valid_from"] = params["slow"] + params["signal"] - 2
        else:
            raise ValueError(f"Unknown feature kind: {kind}")
        feature_params[name] = params

    metadata = build_metadata(
        input_path=str(input_path),
        input_format=input_format,
        input_sha256=input_sha256,
        output_path=str(output_path),
        output_sha256=output_sha256,
        row_count=int(out.shape[0]),
        columns=list(out.columns),
        features=list(FEATURES.keys()),
        feature_params=feature_params,
    )
    write_json(meta_path, metadata)

    report = evaluate_risk(
        out,
        feature_input,
        context=RiskContext(
            run_id=args.run_id,
            workspace=None,
            symbol=args.symbol,
            timeframe=args.timeframe,
        ),
    )
    write_risk_report(report, mode="system")


if __name__ == "__main__":
    main()
