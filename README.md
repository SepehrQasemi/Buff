# Buff

## Overview

Buff is a modular AI-assisted trading system for crypto markets (Binance Futures, 1H timeframe).
The focus is **risk-controlled, explainable, and auditable** decision-making — **not price prediction**.

## Core Principles

- No deterministic price prediction
- No LLM-based execution (chatbot is read-only)
- Strict risk management and safety kill-switches
- Full traceability/explainability via logs and reports
- Reproducible research: fixed datasets, versioned configs, tests

## Architecture

The system is composed of:

- Data Pipeline
- Feature & Regime Engine
- Risk Permission Layer
- Strategy Selector (menu-based; no strategy invention)
- Execution Engine (paper → live)
- Chatbot (Reporting, Teaching, Auditing)

See `ARCHITECTURE.md` for module boundaries and interfaces.

## Data Quality Reporting

The data pipeline ingests OHLCV candles from Binance Futures and generates a deterministic quality report
(`reports/data_quality.json`) based on raw OHLCV only.

The report includes per-symbol and global metrics:

- row counts, first/last timestamps, expected vs missing bars
- gap ranges, duplicates, zero-volume bars
- OHLC sanity checks (high < low, negative prices, NaNs)
- SHA256 checksums of parquet files used

See `docs/artifacts.md` for the full artifact contract.

## Usage

### Download and ingest OHLCV data (1m base)

```bash
python -m src.data.run_ingest --base_timeframe 1m --derived_timeframes 5m,15m,30m,1h,2h,4h,1d,1w,2w,1M,3M,6M,1Y
```

This will:

- Download 1m OHLCV data for configured symbols from 2022-01-01 to present
- Save parquet files to `data/ohlcv/` partitioned by timeframe and symbol
- Generate quality report to `reports/data_quality.json`

### Validate stored OHLCV data

```bash
python -m src.data.validate --data_dir data/ohlcv --timeframes 1m,5m,15m,30m,1h,2h,4h,1d,1w,2w,1M,3M,6M,1Y
```

### Generate deterministic data_quality.json

```bash
python -m src.data.report --symbols BTCUSDT,ETHUSDT --timeframes 1m,5m,15m,30m,1h,2h,4h,1d,1w,2w,1M,3M,6M,1Y --data_dir data/ohlcv --out reports/data_quality.json
```

If `--symbols` or `--timeframes` are omitted, they are auto-detected from `data_dir`.

## Verification (M1)

Run the full offline, deterministic verification workflow:

```bash
python scripts/verify_m1.py
```

### Verify data and report integrity

```bash
python -m src.data.verify_outputs
```

This will:

- Load `reports/data_quality.json`
- Verify that `zero_volume_examples` timestamps exist in data with volume ≤ 0
- Verify that `missing_examples` timestamps do NOT exist in data (correctly marked as missing)
- Print verification results

## Project Status

🚧 Phase 0–1: Repo bootstrap + data pipeline (in progress)

## Disclaimer

This project is for research and educational purposes only. Use at your own risk.
