# Buff

## Overview

Buff is a modular crypto trading system intended for real personal use with real money in the future.
It is designed to be safety-first, audit-first, and fail-closed.

Buff does NOT invent strategies. Users define indicators and strategies, and the system only executes
registered, approved strategies through a controlled pipeline.

## Safety Principles

- Fail-closed everywhere: if inputs are missing or invalid, execution is blocked.
- Risk is a hard veto layer.
- UI and chatbot are read-only for execution and cannot place orders.
- Execution runs independently from UI and requires explicit arming in the control plane.
- Full audit trail for every decision and order action.

## Quickstart

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Quality Gates

```bash
ruff check .
pytest -q
ruff format --check .
```

## Governance / Safety

See SECURITY.md for disclosure and secrets policy. The project forbids prediction or
signal logic and requires deterministic, auditable changes.
## End-to-End Flow

Data -> Features -> Risk -> Strategy Selection -> Execution

- Data: deterministic OHLCV ingest and quality reports
- Features: preset indicators and user-approved indicators
- Risk: permission layer (GREEN/YELLOW/RED)
- Strategy Selection: picks only from registered strategies
- Execution: paper trading first, staged live later

## Done v1.0

- Stable paper trading
- Full audit trail (decision_records.jsonl)
- Deterministic, reproducible runs

## Modes

Manual mode is a sandbox with no effect on the system. It writes only to workspaces/.

Example:

```bash
python -m src.manual.run_manual --workspace demo --symbol BTCUSDT --timeframe 1h
```

## Architecture

- Data Pipeline
- Feature Engine
- Risk Permission Layer
- Strategy Selector (menu-based; no strategy invention)
- Execution Engine (paper -> staged live)
- Control Plane (arming, approvals, kill switch)
- Interface Plane (UI + Chatbot, read-only for execution)

See ARCHITECTURE.md, PROJECT_SCOPE.md, and EXECUTION_SAFETY.md for details.

## Disclaimer

Use at your own risk. This project is intended for real personal use but must be validated
carefully before any live trading.
