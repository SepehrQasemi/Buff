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

### Download and ingest OHLCV data

```bash
python -m src.data.run_ingest
```

This will:

- Download OHLCV data for all 10 symbols (BTC, ETH, BNB, SOL, XRP, ADA, DOGE, TRX, AVAX, LINK) from 2022-01-01 to present
- Save parquet files to `data/clean/`
- Generate quality report to `reports/data_quality.json`

### Validate stored OHLCV data

```bash
python -m src.data.validate --data_dir data/clean --timeframe 1h
```

### Generate deterministic data_quality.json

```bash
python -m src.data.report --symbols BTCUSDT,ETHUSDT --timeframe 1h --data_dir data/clean --out reports/data_quality.json
```

If `--symbols` is omitted, symbols are auto-detected from `data_dir`.

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
