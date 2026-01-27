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

- Partitioned by timeframe and symbol directories.
- One file per (symbol, timeframe).

## Naming Conventions

Directory layout:

```
data/ohlcv/timeframe=1m/symbol=BTCUSDT/ohlcv.parquet
data/ohlcv/timeframe=1h/symbol=BTCUSDT/ohlcv.parquet
```

Symbols are stored in CCXT format (`BTC/USDT`) and converted to partition names by removing `/`.

## Timeframes

- Base timeframe: `1m` (single source of truth)
- Derived timeframes are deterministic resamples of `1m`:
  - Fixed-duration: `5m, 15m, 30m, 1h, 2h, 4h, 1d, 1w, 2w`
  - Calendar-based: `1M, 3M, 6M, 1Y`

## Guarantees (M1)

- Raw 1m OHLCV data is stored deterministically as parquet.
- All derived timeframes are deterministic resamples of 1m.
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
