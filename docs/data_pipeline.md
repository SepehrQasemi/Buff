# Data Pipeline (M1)

This milestone builds a canonical, deterministic 1m OHLCV dataset for Binance USDT-M Futures.

## Run

```bash
python -m src.data.ingest --symbols BTCUSDT ETHUSDT --since 2024-01-01T00:00:00Z --end 2024-01-03T00:00:00Z --out data --report reports/data_quality.json
```

## Artifacts

- Parquet: `data/ohlcv_1m/{SYMBOL}.parquet`
- Report: `reports/data_quality.json`

## Invariants

- Timeframe is fixed to `1m`.
- UTC everywhere; timestamps are epoch milliseconds aligned to minute boundaries.
- Strict validation: gaps, duplicates, misalignment, zero volume, or candle integrity violations fail.
- Deterministic storage: sorted by `["symbol", "timestamp"]`, stable schema, `zstd` compression.
