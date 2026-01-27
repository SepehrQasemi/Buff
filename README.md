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

## Project Status
🚧 Phase 0–1: Repo bootstrap + data pipeline (in progress)

## Disclaimer
This project is for research and educational purposes only. Use at your own risk.
