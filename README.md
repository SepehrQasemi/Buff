# Buff

## Overview

Buff is a modular AI-assisted trading research system for crypto markets (Binance Futures),
built around a **1m source-of-truth OHLCV dataset** with deterministic multi-timeframe
derivations (e.g., 5m–1H–1D).

The focus is **risk-controlled, explainable, and auditable decision-making** — not price prediction.

## Core Principles

- No deterministic price prediction
- No LLM-based execution (chatbot is read-only)
- Strict risk management and safety kill-switches
- Full traceability and explainability via logs and reports
- Reproducible research: fixed datasets, versioned configs, tests

## Modes: Manual vs System

Manual mode is a sandbox with no effect on the system.
It writes only to `workspaces/`.

Example:

```bash
python -m src.manual.run_manual --workspace demo --symbol BTCUSDT --timeframe 1h
```

## Architecture

The system is composed of:

- Data Pipeline
- Feature & Regime Engine
- Risk Permission Layer
- Strategy Selector (menu-based; no strategy invention)
- Execution Engine: paper trading → live (planned, not implemented)
- Chatbot (Reporting, Teaching, Auditing)

See `ARCHITECTURE.md` for module boundaries and interfaces, and
`docs/features.md` for the feature-engine contract.

## Data Quality Reporting

The data pipeline ingests OHLCV candles from Binance Futures and generates a
**deterministic quality report** (`reports/data_quality.json`) based on raw OHLCV only.

The report includes per-symbol and global metrics:

- Row counts, first/last timestamps, expected vs missing bars
- Gap ranges, duplicates, non-positive volume bars (volume ≤ 0)
- OHLC sanity checks (high < low, negative prices, NaNs)
- SHA256 checksums of parquet files used

See `docs/artifacts.md` for the full artifact contract.

## Usage

### Download and ingest OHLCV data (1m base)

```bash
python -m src.data.run_ingest \
  --base_timeframe 1m \
  --derived_timeframes 5m,15m,30m,1h,2h,4h,1d,1w,2w,1M,3M,6M,1Y
```

This will:

- Download **1m OHLCV** data for configured symbols from 2022-01-01 to present
- Save parquet files to `data/ohlcv/`, partitioned by timeframe and symbol
- Generate a deterministic quality report at `reports/data_quality.json`

### Validate stored OHLCV data

```bash
python -m src.data.validate \
  --data_dir data/ohlcv \
  --timeframes 1m,5m,15m,30m,1h,2h,4h,1d,1w,2w,1M,3M,6M,1Y
```

Validation rules include:

- Required OHLCV columns must be present
- Timestamps must be strictly increasing and unique
- Prices must be non-negative and finite
- Volume must be strictly positive (volume > 0)

### Generate deterministic `data_quality.json`

```bash
python -m src.data.report \
  --symbols BTCUSDT,ETHUSDT \
  --timeframes 1m,5m,15m,30m,1h,2h,4h,1d,1w,2w,1M,3M,6M,1Y \
  --data_dir data/ohlcv \
  --out reports/data_quality.json
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
- Verify that zero-volume example timestamps exist in data with volume ≤ 0
- Verify that missing example timestamps do not exist in data
- Print verification results

## Feature Engine (M4.1 / M4.2)

The feature engine produces **deterministic, preset-only indicators**
from validated OHLCV input.

### Presets (Tier-1)

Preset: ema_20  
Inputs: close  
Outputs: ema_20  
Params: period=20  

Preset: rsi_14  
Inputs: close  
Outputs: rsi_14  
Params: period=14  

Preset: atr_14  
Inputs: high, low, close  
Outputs: atr_14  
Params: period=14  

Preset: sma_20  
Inputs: close  
Outputs: sma_20  
Params: period=20  

Preset: std_20  
Inputs: close  
Outputs: std_20  
Params: period=20, ddof=0  

Preset: bbands_20_2  
Inputs: close  
Outputs: bb_mid_20_2, bb_upper_20_2, bb_lower_20_2  
Params: period=20, k=2.0, ddof=0  

Preset: macd_12_26_9  
Inputs: close  
Outputs: macd_12_26_9, macd_signal_12_26_9, macd_hist_12_26_9  
Params: fast=12, slow=26, signal=9  

### CLI

```bash
python -m src.buff.cli features <input_path> <output_path> [--meta <meta_path>]
```

### Train vs Live Modes

- train (default): no trimming; legacy-compatible behavior
- live: no trimming; output length equals input length; warmup NaNs preserved

Validity metadata is recorded per preset in `feature_params` using the reserved key
`_valid_from` (first reliable index). See `docs/features.md`.

### Goldens

Golden outputs live at `tests/goldens/expected.csv`.
Tests compare indicator outputs and runner output against these goldens.
See `docs/goldens.md`.

## Project Status

- Data pipeline, data contracts, and deterministic reporting: implemented
- Feature engine with Tier-1 presets: implemented
- Dual-mode feature runner (train/live) with validity metadata: implemented
- Dataset builder and model training: planned next

## Disclaimer

This project is for research and educational purposes only.
Use at your own risk.

