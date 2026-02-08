# PROJECT_SCOPE v1.0 - Buff

## Goals
- User-defined indicators and strategies
- TradingView-like strategy analysis lab (chart-first, visual signals/trades/outcomes)
- Read-only UI: no buy/sell buttons, broker connections, or live execution controls
- Menu-based strategy selection (no invention)
- Deterministic, auditable pipeline
- Canonical 1m market data ingest with deterministic resampling to higher timeframes

## Non-Goals
- Price prediction or AI forecasting
- Autonomous strategy generation by AI or LLMs (chatbot may provide templates based on user-defined rules)
- Direct UI-triggered order placement or live execution controls
- Broker connections or live trading controls in UI
- Multi-tenant SaaS or hosted user accounts (v1)
- Hidden execution logic

## Separation of Planes

- Sandbox: user authoring and experiments, no live execution
- Control Plane: arming/disarming, approvals, kill switch
- Execution Plane: broker interaction, risk-locked order flow

The UI and chatbot are interface-only and cannot place orders directly.
Phase-0 product scope is read-only; broker/execution integrations are out of scope.

## References
- `docs/PROJECT_SPEC.md`
- `docs/data_timeframes.md`
