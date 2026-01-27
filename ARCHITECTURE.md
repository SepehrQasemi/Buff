# ARCHITECTURE — Buff

## Separation of Concerns
The system is split into two layers:
1) Core Trading System (money-sensitive; deterministic where possible)
2) Chatbot Layer (read-only; reporting/teaching/auditing)

## Core Modules
- src/data: ingest/validate/store
- src/features: indicators, feature set, regime detection
- src/risk: permission layer (green/yellow/red)
- src/selector: selects from predefined strategies
- src/strategies: strategy interface + implementations
- src/execution: order manager, position sizing, safety checks

## Chatbot Module
- src/chatbot: prompts + tools for reporting/teaching/auditing
- Must not have any execution privileges

## Interfaces (v0.1)
- Data → Features: cleaned OHLCV parquet
- Features → Selector: market_state_vector
- Risk → Selector: risk_state
- Selector → Execution: strategy_id + signal (later), guarded by risk manager
