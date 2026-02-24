ARCHIVED — NOT AUTHORITATIVE
Superseded by new documentation reset 2026-02-24.
Do not rely on this file for current stage or product direction.

# Appendix: Artifacts Notes (Historical Detailed Notes)

Historical source retained from `docs/artifacts.md` before PR2 contract unification.
Canonical run artifact requirements now live in [../03_CONTRACTS_AND_SCHEMAS.md](../03_CONTRACTS_AND_SCHEMAS.md).

---

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
- M1 canonical 1m pipeline writes a single timeframe dataset under `data/ohlcv_1m/`.

## Naming Conventions

Directory layout:

```
data/ohlcv_1m/BTCUSDT.parquet
data/ohlcv/timeframe=1m/symbol=BTCUSDT/ohlcv.parquet
data/ohlcv/timeframe=1h/symbol=BTCUSDT/ohlcv.parquet
```

Symbols are stored in CCXT format (`BTC/USDT`) and converted to partition names by removing `/`.

## Timeframes

- Base timeframe: `1m` (single source of truth)
- Derived timeframes are deterministic resamples of `1m`:
  - Fixed-duration: `5m, 15m, 30m, 1h, 2h, 4h, 1d, 1w, 2w`
  - Calendar-based: `1M, 3M, 6M, 1Y`
- See `docs/data_timeframes.md` for exact aggregation rules and edge cases.

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
- No derived datasets in the M1 ingest pipeline (derived timeframes are produced by the multi-timeframe runner)

## Layer-1 Run Artifacts (RUNS_ROOT)

Layer-1 runs write artifacts directly under `RUNS_ROOT/<run_id>/` and are read by the API.

Historical required artifacts snapshot:

- `manifest.json`
- `config.json`
- `metrics.json`
- `equity_curve.json`
- `decision_records.jsonl`
- `trades.jsonl`
- `timeline.json`
- `ohlcv_*.jsonl` (for example `ohlcv_1m.jsonl`)

JSONL formats (one JSON object per line):

- `trades.jsonl` includes `entry_time`, `exit_time`, `entry_price`, `exit_price`, `side`, `qty`, `pnl`, `fees`.
- `ohlcv_*.jsonl` includes `ts`, `open`, `high`, `low`, `close`, `volume`.

JSON formats:

- `metrics.json` is a single JSON object with summary statistics. Required fields for UI: `total_return`, `max_drawdown`, `num_trades`, `win_rate` (additional fields like `final_equity`, `risk_level`, `symbol` may be present).
- `timeline.json` is a JSON array of event objects. Each event includes `timestamp`, `type`, `title`, and `severity` (optional `detail`).

Precedence:

- If a parquet artifact exists in the run directory (for example `trades.parquet` or `ohlcv_1m.parquet`), the API prefers parquet.
- Otherwise the API reads the JSONL artifacts above.
