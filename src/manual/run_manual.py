"""Manual analysis mode CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from buff.data.store import load_parquet, ohlcv_parquet_path
from buff.features.runner import run_features
from risk.evaluator import evaluate_risk
from risk.report import write_risk_report
from risk.types import RiskContext
from utils.path_guard import guard_manual_write


def _normalize_symbol(symbol: str) -> str:
    if "/" in symbol:
        return symbol
    if symbol.endswith("USDT") and len(symbol) > 4:
        return f"{symbol[:-4]}/USDT"
    return symbol


def _parse_timestamp(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    return pd.to_datetime(value, utc=True)


def _load_ohlcv(data_dir: Path, symbol: str, timeframe: str) -> pd.DataFrame:
    path = ohlcv_parquet_path(data_dir, symbol, timeframe)
    if not path.exists():
        return pd.DataFrame()
    df = load_parquet(str(path))
    if "ts" not in df.columns and "timestamp" not in df.columns:
        raise ValueError("OHLCV data must include 'ts' or 'timestamp' column")
    return df


def _filter_time_range(
    df: pd.DataFrame, start: pd.Timestamp | None, end: pd.Timestamp | None
) -> pd.DataFrame:
    if start is None and end is None:
        return df
    ts_col = "ts" if "ts" in df.columns else "timestamp"
    ts = pd.to_datetime(df[ts_col], utc=True)
    mask = pd.Series(True, index=df.index)
    if start is not None:
        mask &= ts >= start
    if end is not None:
        mask &= ts <= end
    return df.loc[mask].copy()


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual analysis mode session")
    parser.add_argument("--workspace", type=str, required=True, help="Workspace name")
    parser.add_argument("--symbol", type=str, required=True, help="Symbol (e.g., BTCUSDT)")
    parser.add_argument("--timeframe", type=str, required=True, help="Timeframe (e.g., 1h)")
    parser.add_argument("--from", dest="start", type=str, help="Start timestamp (ISO)")
    parser.add_argument("--to", dest="end", type=str, help="End timestamp (ISO)")
    parser.add_argument(
        "--data_dir", type=str, default="data/ohlcv", help="Base OHLCV data directory"
    )
    parser.add_argument("--run_id", type=str, default=None, help="Optional run id")
    args = parser.parse_args()

    symbol = _normalize_symbol(args.symbol)
    start_ts = _parse_timestamp(args.start)
    end_ts = _parse_timestamp(args.end)
    data_dir = Path(args.data_dir)

    session = {
        "workspace": args.workspace,
        "symbol": symbol,
        "timeframe": args.timeframe,
        "start_ts": args.start,
        "end_ts": args.end,
        "indicator_params": {},
    }

    session_path = Path("workspaces") / args.workspace / "session.json"
    # All file writes MUST go through path_guard to preserve mode separation.
    target = guard_manual_write(session_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")

    ohlcv = _load_ohlcv(data_dir, symbol, args.timeframe)
    ohlcv = _filter_time_range(ohlcv, start_ts, end_ts)

    context = RiskContext(
        run_id=args.run_id,
        workspace=args.workspace,
        symbol=symbol,
        timeframe=args.timeframe,
    )

    if ohlcv.empty:
        report = evaluate_risk(pd.DataFrame(), ohlcv, context=context)
        write_risk_report(report, mode="manual")
        return

    features_input = ohlcv.copy()
    if "timestamp" not in features_input.columns and "ts" in features_input.columns:
        features_input = features_input.rename(columns={"ts": "timestamp"})

    features = run_features(features_input)

    report = evaluate_risk(features, features_input, context=context)
    write_risk_report(report, mode="manual")


if __name__ == "__main__":
    main()
