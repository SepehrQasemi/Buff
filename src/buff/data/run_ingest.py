"""CLI runner for OHLCV ingest and data quality reporting."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from buff.data.ingest import IngestConfig, fetch_ohlcv_all, make_exchange
from buff.data.store import save_parquet, symbol_to_filename
from buff.data.validate import compute_quality


def main() -> None:
    """Download OHLCV data for all symbols, save to parquet, and write quality report."""
    # Configuration
    symbols = [
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
    start_date = datetime(2022, 1, 1, tzinfo=timezone.utc)
    start_ms = int(start_date.timestamp() * 1000)
    timeframe = "1h"

    cfg = IngestConfig(exchange="binance", market_type="future", timeframe=timeframe)
    exchange = make_exchange(cfg)

    # Create data/clean directory
    data_dir = Path("data/clean")
    data_dir.mkdir(parents=True, exist_ok=True)

    # Create reports directory
    reports_dir = Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Download and process each symbol
    reports = {}
    for symbol in symbols:
        print(f"\nFetching {symbol}...")
        try:
            df = fetch_ohlcv_all(
                exchange, symbol, timeframe, start_ms, limit=cfg.limit
            )

            # Compute quality metrics
            quality = compute_quality(df, timeframe)

            # Save parquet
            filename = symbol_to_filename(symbol, timeframe)
            filepath = data_dir / filename
            save_parquet(df, str(filepath))

            # Build report
            reports[symbol] = {
                "rows": quality.rows,
                "start_ts": quality.start_ts,
                "end_ts": quality.end_ts,
                "duplicates": quality.duplicates,
                "missing_candles": quality.missing_candles,
                "missing_examples": quality.missing_examples,
                "zero_volume": quality.zero_volume,
                "zero_volume_examples": quality.zero_volume_examples,
                "file": str(filename),
            }

            # Print detailed progress
            print(f"  ✓ Saved {filename}")
            print(f"    Rows: {quality.rows}")
            print(f"    Start: {quality.start_ts}")
            print(f"    End: {quality.end_ts}")
            if quality.duplicates > 0:
                print(f"    Duplicates: {quality.duplicates}")
            if quality.missing_candles > 0:
                print(f"    Missing candles: {quality.missing_candles}")
                if quality.missing_examples:
                    print(f"      Examples: {quality.missing_examples[:2]}")
            if quality.zero_volume > 0:
                print(f"    Zero volume: {quality.zero_volume}")
                if quality.zero_volume_examples:
                    print(f"      Examples: {quality.zero_volume_examples[:2]}")
        except Exception as e:
            print(f"  ✗ Error: {e}")
            reports[symbol] = {"error": str(e)}

    # Write report to JSON
    report_path = reports_dir / "data_quality.json"
    with open(report_path, "w") as f:
        json.dump(reports, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Saved report to {report_path}")
    print("Report includes example timestamps: missing_examples, zero_volume_examples")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
