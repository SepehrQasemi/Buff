# PROJECT_SPEC - Buff

This document is the single source of truth for Buff's current behavior.
All DONE statements cite file paths as evidence. PLANNED items are explicitly labeled.

## Status Legend
- DONE = implemented and verified in code/tests.
- PLANNED = described/spec'd but not implemented.

## Canonical Data Rule (Non-Negotiable)
- Base market data timeframe is **1m**.
- All higher timeframes are derived deterministically from 1m via resampling/aggregation.
- See `docs/data_timeframes.md` for exact rules and edge cases.
  Evidence: `src/ta/timeframes.py`, `src/buff/data/run_ingest.py`, `src/data/ingest.py`.

## Determinism Guarantees (DONE)
- Canonical JSON serialization with sorted keys and quantized floats for audit/replay artifacts.
  Evidence: `src/audit/canonical_json.py`, `src/audit/decision_record.py`, `tests/test_decision_record_canonicalization.py`.
- Deterministic 1m parquet ordering and schema for canonical ingest.
  Evidence: `src/data/store.py`, `tests/test_data_m1_reproducibility.py`.
- Deterministic resampling outputs and stable windowing from 1m.
  Evidence: `src/buff/data/resample.py` (`resample_ohlcv`, `resample_fixed`, `resample_calendar`), `tests/test_resample.py`.
- Stable reason codes for execution gating and risk locks (fail-closed semantics).
  Evidence: `src/execution/engine.py`, `src/execution/locks.py`.

## Safety & Governance Model (DONE)
- Control plane arming is required for execution; missing/invalid state fails closed.
  Evidence: `src/control_plane/control.py`, `src/control_plane/persistence.py`.
- Risk veto and lock enforcement block execution on RED or missing limits.
  Evidence: `src/execution/gate.py`, `src/execution/locks.py`, `src/risk/state_machine.py`.
- UI/chatbot do not place orders directly; execution flows through control plane.
  Evidence: `src/ui/api.py`, `src/chatbot/cli.py`, `src/control_plane/core.py`.
- Full audit trail via decision records, snapshots, and replay verification.
  Evidence: `src/audit/decision_record.py`, `src/audit/replay.py`, `docs/DECISION_RECORD.md`.

## Current System Behavior

### DONE (Implemented)
- **Canonical 1m ingest (M1)**: fetches Binance Futures 1m candles, validates strict 1m invariants, writes deterministic parquet to `data/ohlcv_1m`.
  Evidence: `src/data/ingest.py`, `src/data/validate.py`, `src/data/store.py`, `tests/test_data_m1_validation.py`.
- **Multi-timeframe pipeline**: enforces 1m base timeframe and derives fixed + calendar timeframes by deterministic resampling; stores partitioned parquet under `data/ohlcv/timeframe=...`.
  Evidence: `src/buff/data/run_ingest.py`, `src/buff/data/resample.py`, `src/buff/data/store.py`.
- **Resampling implementation**: deterministic OHLCV aggregation and windowing.
  Evidence: `src/buff/data/resample.py` (`_aggregate_ohlcv`, `resample_ohlcv`, `resample_fixed`, `resample_calendar`).
- **Data quality reporting**: deterministic report generation and schema validation for OHLCV datasets.
  Evidence: `src/buff/data/report.py`, `schemas/data_quality.schema.json`, `tests/test_report_schema.py`.
- **Feature engine**: deterministic indicator computation with registry-defined outputs and metadata.
  Evidence: `src/buff/features/registry.py`, `src/buff/features/runner.py`, `tests/test_feature_runner_e2e.py`.
- **Risk permission layer**: computes RED/YELLOW/GREEN, emits risk reports, and enforces vetoes.
  Evidence: `src/risk/evaluator.py`, `src/risk/policy.py`, `schemas/risk_report.schema.json`.
- **Fundamental risk engine**: rule-based evaluator with offline snapshot provider; optionally integrated into execution.
  Evidence: `src/risk_fundamental/engine.py`, `src/risk_fundamental/providers/offline.py`, `src/risk_fundamental/integration.py`.
- **Strategy selection (menu-based)**: deterministic selector that only chooses from registered strategy IDs.
  Evidence: `src/selector/selector.py`, `src/strategies/menu.py`, `tests/test_selector.py`.
- **Strategy registry (approval gating for control plane)**: in-memory registry with versioned specs and approval checks.
  Evidence: `src/strategies/registry.py`, `src/control_plane/core.py`.
- **Strategy metadata registry (auxiliary)**: deterministic ordering for registered strategy specs.
  Evidence: `src/strategy_registry/registry.py`, `tests/strategy_registry/test_registry.py`.
- **Execution engine (paper)**: idempotent intent handling, risk gating, lock enforcement, and decision logging.
  Evidence: `src/execution/engine.py`, `src/execution/idempotency_sqlite.py`, `src/execution/audit.py`.
- **Control plane**: arming/approvals/kill switch gating for paper execution.
  Evidence: `src/control_plane/core.py`, `src/control_plane/state.py`.
- **Audit tooling (M7)**: decision records, snapshots, replay verification, migration tools, and CLIs.
  Evidence: `src/audit/decision_record.py`, `src/audit/replay.py`, `src/audit/migrate_records.py`.
- **Read-only audit interfaces**: chatbot CLI and workspace/report tooling for inspection.
  Evidence: `src/chatbot/cli.py`, `src/workspaces/indexer.py`, `src/reports/decision_report.py`.
- **Regime classification tools**: YAML-driven regime evaluation and CLI access.
  Evidence: `src/buff/regimes/evaluator.py`, `src/buff/cli.py`, `knowledge/regimes.yaml`.

### PLANNED / Not Implemented
- **Live broker/execution path**: live broker is a stub; no live order routing.
  Evidence: `src/execution/brokers.py`.
- **UI backtest runner**: explicit NotImplemented stub in UI API.
  Evidence: `src/ui/api.py`.
- **Automated market-state rule evaluation from `knowledge/market_state_rules.yaml`**: rules exist and are validated, but no engine consumes them.
  Evidence: `knowledge/market_state_rules.yaml`, `tests/test_market_state_rules.py`.
- **Live fundamental data providers**: provider interface exists; only offline fixture provider is implemented.
  Evidence: `src/risk_fundamental/providers/base.py`, `src/risk_fundamental/providers/offline.py`.

## Related Docs
- `docs/data_timeframes.md` (canonical timeframe rules)
- `docs/REPLAY.md` (replay semantics)
- `docs/RISK_POLICY.md` (risk policy details)
- `docs/REGIME_SEMANTICS.md` (regime definitions)
