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

The data pipeline ingests OHLCV candles from Binance Futures and generates a detailed quality report (`reports/data_quality.json`).

Beyond reporting error counts, the quality report includes **example timestamps** (up to 5 per issue type) for rapid debugging:

- **missing_candles**: Count of gaps in candle sequence
  - **missing_examples**: Sample timestamps of candles that should exist but are absent
- **zero_volume**: Count of candles with zero or negative volume
  - **zero_volume_examples**: Sample timestamps of affected candles

For example, if a data gap is detected:

```json
{
  "missing_candles": 2,
  "missing_examples": [
    "2023-03-24 02:00:00+00:00",
    "2023-03-24 13:00:00+00:00"
  ],
  "zero_volume": 1,
  "zero_volume_examples": ["2023-03-24 12:00:00+00:00"]
}
```

**Important:** These data quality issues are **reported but not removed**. All raw candles are preserved in the parquet files; quality metrics are informational only.

## Usage

### Download and ingest OHLCV data

```bash
python -m src.data.run_ingest
```

This will:

- Download OHLCV data for all 10 symbols (BTC, ETH, BNB, SOL, XRP, ADA, DOGE, TRX, AVAX, LINK) from 2022-01-01 to present
- Save parquet files to `data/clean/`
- Generate quality report to `reports/data_quality.json`

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
