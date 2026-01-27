"""CLI runner for OHLCV ingest and data quality reporting."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from buff.data.ingest import IngestConfig, fetch_ohlcv_all, make_exchange
from buff.data.report import build_report, write_report
from buff.data.store import save_parquet, symbol_to_filename
from buff.data.validate import compute_quality


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
    """Download OHLCV data for symbols, save to parquet, and write quality report."""
    parser = argparse.ArgumentParser(description="OHLCV ingest and data quality report")
    parser.add_argument("--symbols", type=str, default="", help="Comma-separated symbols")
    parser.add_argument("--timeframe", type=str, default="1h", help="Timeframe (e.g., 1h)")
    parser.add_argument(
        "--start_date",
        type=str,
        default="2022-01-01",
        help="Start date (YYYY-MM-DD) for online ingest",
    )
    parser.add_argument("--data_dir", type=str, default="data/clean", help="Output data dir")
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

    args = parser.parse_args()

    symbols = _parse_symbols(args.symbols)
    timeframe = args.timeframe

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

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
            timeframe=timeframe,
            limit=args.limit,
        )
        exchange = make_exchange(cfg)

    saved_symbols = []
    for symbol in symbols:
        print(f"\nFetching {symbol}...")
        try:
            if args.offline:
                df = _load_fixture(Path(args.fixtures_dir), symbol, timeframe)
            else:
                df = fetch_ohlcv_all(exchange, symbol, timeframe, start_ms, limit=args.limit)

            quality = compute_quality(df, timeframe)

            filename = symbol_to_filename(symbol, timeframe)
            filepath = data_dir / filename
            save_parquet(df, str(filepath))

            saved_symbols.append(symbol)

            print(f"  OK Saved {filename}")
            print(f"    Rows: {quality.rows}")
            print(f"    Start: {quality.start_ts}")
            print(f"    End: {quality.end_ts}")
            if quality.duplicates > 0:
                print(f"    Duplicates: {quality.duplicates}")
            if quality.missing_candles > 0:
                print(f"    Missing candles: {quality.missing_candles}")
            if quality.zero_volume > 0:
                print(f"    Zero volume: {quality.zero_volume}")
        except Exception as e:
            print(f"  ERROR: {e}")

    report_path = reports_dir / "data_quality.json"
    if saved_symbols:
        report = build_report(data_dir, saved_symbols, timeframe, strict=False)
        write_report(report, report_path)
    else:
        report_path.write_text("{}", encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"Saved report to {report_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
