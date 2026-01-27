# Artifacts (M1)

## OHLCV Parquet Schema

Each parquet file contains raw OHLCV candles with these columns:

- `ts` (datetime64[ns, UTC]) Candle open timestamp
- `open` (float)
- `high` (float)
- `low` (float)
- `close` (float)
- `volume` (float)

## Partitioning Strategy

- Partitioned by symbol and timeframe at the file level.
- One file per (symbol, timeframe).

## Naming Conventions

Parquet filename format:

```
{SYMBOL}_{QUOTE}_{TIMEFRAME}.parquet
```

Examples:

- `BTC_USDT_1h.parquet`
- `ETH_USDT_1h.parquet`

Symbols are stored in CCXT format (`BTC/USDT`) and converted to filenames by replacing `/` with `_`.

## Guarantees (M1)

- Raw OHLCV data is stored deterministically as parquet.
- Deterministic, reproducible `reports/data_quality.json` is generated from raw OHLCV only.
- Data quality report includes:
  - row counts, time range, expected vs missing bars
  - gap ranges, duplicates, zero-volume bars
  - OHLC sanity checks (high < low, negative prices, NaNs)
  - per-file SHA256 checksums

## Explicit Non-Goals (M1)

- No indicators or features
- No strategy logic or ML
- No trading decisions
- No derived datasets
