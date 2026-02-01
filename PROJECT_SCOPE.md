# PROJECT_SCOPE v1.0 - Buff

## Goals
- User-defined indicators and strategies
- Menu-based strategy execution (no invention)
- Safe path to auto-trading: paper -> staged live -> production live
- Deterministic, auditable pipeline
- Canonical 1m market data ingest with deterministic resampling to higher timeframes

## Non-Goals
- Price prediction or AI forecasting
- Strategy generation by AI or LLMs
- Direct UI-triggered order placement
- Hidden execution logic

## Separation of Planes

- Sandbox: user authoring and experiments, no live execution
- Control Plane: arming/disarming, approvals, kill switch
- Execution Plane: broker interaction, risk-locked order flow

The UI and chatbot are interface-only and cannot place orders directly.

## References
- `docs/PROJECT_SPEC.md`
- `docs/data_timeframes.md`
