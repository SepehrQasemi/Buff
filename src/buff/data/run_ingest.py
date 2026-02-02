"""CLI runner for OHLCV ingest and data quality reporting."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path

import pandas as pd

from buff.data.ingest import IngestConfig, fetch_ohlcv_all, make_exchange
from buff.data.report import build_report, write_report
from buff.data.resample import resample_ohlcv
from buff.data.store import ohlcv_parquet_path, save_parquet, symbol_to_filename
from buff.data.validate import compute_quality
from buff.data.quality_report import build_quality_report, write_quality_report


DEFAULT_SYMBOLS = [
    "BTC/USDT",
    "ETH/USDT",
    "BNB/USDT",
    "SOL/USDT",
    "XRP/USDT",
    "ADA/USDT",
    "DOGE/USDT",
    "TRX/USDT",
    "AVAX/USDT",
    "LINK/USDT",
]

DEFAULT_DERIVED_TIMEFRAMES = [
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "1d",
    "1w",
    "2w",
    "1M",
    "3M",
    "6M",
    "1Y",
]


def _normalize_symbol(symbol: str) -> str:
    if "/" in symbol:
        return symbol
    if symbol.endswith("USDT") and len(symbol) > 4:
        return f"{symbol[:-4]}/USDT"
    return symbol


def _parse_symbols(raw: str) -> list[str]:
    if not raw:
        return DEFAULT_SYMBOLS.copy()
    return [_normalize_symbol(sym.strip()) for sym in raw.split(",") if sym.strip()]


def _parse_timeframes(raw: str) -> list[str]:
    if not raw:
        return []
    return [tf.strip() for tf in raw.split(",") if tf.strip()]


def _load_fixture(fixtures_dir: Path, symbol: str, timeframe: str) -> pd.DataFrame:
    filename = symbol_to_filename(symbol, timeframe)
    csv_path = fixtures_dir / filename.replace(".parquet", ".csv")
    parquet_path = fixtures_dir / filename

    if csv_path.exists():
        df = pd.read_csv(csv_path)
    elif parquet_path.exists():
        df = pd.read_parquet(parquet_path, engine="pyarrow")
    else:
        raise FileNotFoundError(f"Missing fixture for {symbol}: {csv_path} or {parquet_path}")

    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def main() -> None:
    """Download OHLCV 1m data for symbols, resample, and write quality report."""
    parser = argparse.ArgumentParser(description="OHLCV ingest and data quality report")
    parser.add_argument("--symbols", type=str, default="", help="Comma-separated symbols")
    parser.add_argument("--base_timeframe", type=str, default="1m", help="Base timeframe")
    parser.add_argument(
        "--derived_timeframes",
        type=str,
        default=",".join(DEFAULT_DERIVED_TIMEFRAMES),
        help="Comma-separated derived timeframes",
    )
    parser.add_argument(
        "--timeframes",
        type=str,
        default="",
        help="Override list of timeframes to output (includes base if omitted)",
    )
    parser.add_argument(
        "--start_date",
        type=str,
        default="2022-01-01",
        help="Start date (YYYY-MM-DD) for online ingest",
    )
    parser.add_argument("--data_dir", type=str, default="data/ohlcv", help="Output base dir")
    parser.add_argument("--reports_dir", type=str, default="reports", help="Output reports dir")
    parser.add_argument("--offline", action="store_true", help="Use local fixtures")
    parser.add_argument(
        "--fixtures_dir",
        type=str,
        default="tests/fixtures/ohlcv",
        help="Fixture directory for offline mode",
    )
    parser.add_argument("--exchange", type=str, default="binance", help="Exchange name")
    parser.add_argument("--market_type", type=str, default="future", help="Market type")
    parser.add_argument("--limit", type=int, default=1000, help="Fetch limit per request")
    parser.add_argument("--run_id", type=str, default="", help="Workspace run id for snapshot")

    args = parser.parse_args()

    symbols = _parse_symbols(args.symbols)
    base_timeframe = args.base_timeframe

    if base_timeframe != "1m":
        raise ValueError("Base timeframe must be 1m")

    if args.run_id and len(symbols) != 1:
        raise ValueError("run_id requires exactly one symbol")

    if args.timeframes:
        timeframes = _parse_timeframes(args.timeframes)
    else:
        timeframes = [base_timeframe] + _parse_timeframes(args.derived_timeframes)

    if base_timeframe not in timeframes:
        timeframes = [base_timeframe] + timeframes

    data_dir = Path(args.data_dir)
    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    exchange = None
    start_ms = None
    if not args.offline:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        start_ms = int(start_date.timestamp() * 1000)
        cfg = IngestConfig(
            exchange=args.exchange,
            market_type=args.market_type,
            timeframe=base_timeframe,
            limit=args.limit,
        )
        exchange = make_exchange(cfg)

    saved_symbols = []
    workspace_report: dict[str, object] | None = None
    for symbol in symbols:
        print(f"\nFetching base {base_timeframe} for {symbol}...")
        try:
            if args.offline:
                base_df = _load_fixture(Path(args.fixtures_dir), symbol, base_timeframe)
            else:
                base_df = fetch_ohlcv_all(
                    exchange, symbol, base_timeframe, start_ms, limit=args.limit
                )

            base_df = base_df.sort_values("ts").reset_index(drop=True)
            base_path = ohlcv_parquet_path(data_dir, symbol, base_timeframe)
            save_parquet(base_df, str(base_path))

            if args.run_id:
                workspaces_dir = Path(os.getenv("BUFF_WORKSPACES_DIR", "workspaces"))
                run_dir = workspaces_dir / args.run_id
                run_dir.mkdir(parents=True, exist_ok=True)
                snapshot_path = run_dir / "ohlcv_1m.parquet"
                save_parquet(base_df, str(snapshot_path))
                workspace_report = build_quality_report(base_df, symbol, base_timeframe)

            for tf in timeframes:
                if tf == base_timeframe:
                    df_tf = base_df
                else:
                    result = resample_ohlcv(base_df, tf)
                    df_tf = result.df

                tf_path = ohlcv_parquet_path(data_dir, symbol, tf)
                save_parquet(df_tf, str(tf_path))

                quality = compute_quality(df_tf, tf)
                print(f"  OK {symbol} {tf} rows={quality.rows}")

            saved_symbols.append(symbol)
        except Exception as e:
            print(f"  ERROR: {e}")

    report_path = reports_dir / "data_quality.json"
    if saved_symbols:
        report = build_report(data_dir, saved_symbols, timeframes, strict=False)
        write_report(report, report_path)
    else:
        report_path.write_text("{}", encoding="utf-8")

    if args.run_id and workspace_report is not None:
        workspaces_dir = Path(os.getenv("BUFF_WORKSPACES_DIR", "workspaces"))
        run_dir = workspaces_dir / args.run_id
        write_quality_report(run_dir / "data_quality.json", workspace_report)

    print(f"\n{'=' * 60}")
    print(f"Saved report to {report_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
