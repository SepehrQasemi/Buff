# ARCHITECTURE - Buff

## Planes

A) Core/Data Plane
- data: ingest/validate/store (canonical 1m base; derived timeframes via deterministic resampling)
- features: indicators, feature sets
- risk: permission layer (green/yellow/red)
- selector: selects from registered strategies
- execution: order manager, state machine, safety checks

B) Control Plane
- arming/disarming execution
- approvals and limits
- kill switch

C) Interface Plane
- UI + Chatbot
- read-only for execution
- can run sandbox authoring and paper/backtest via control plane

## Rules
- Risk can veto everything.
- Execution runs independently from UI.
- UI and chatbot cannot place orders directly.

## Interfaces
- Data -> Features: validated OHLCV
- Features -> Risk: feature frame + metadata
- Risk -> Selector: risk_state
- Selector -> Execution: strategy_id + intent (LONG/SHORT/FLAT)
- Control Plane -> Execution: arming, limits, kill switch

## References
- `docs/PROJECT_SPEC.md`
- `docs/data_timeframes.md`
