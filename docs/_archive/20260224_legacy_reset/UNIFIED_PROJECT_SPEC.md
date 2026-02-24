ARCHIVED — NOT AUTHORITATIVE
Superseded by new documentation reset 2026-02-24.
Do not rely on this file for current stage or product direction.

# UNIFIED_PROJECT_SPEC

## Metadata
- Branch: feat/mvp-smoke. (Evidence: `.git/HEAD#L1`)
- Commit (current HEAD) is stored in `.git/refs/heads/feat/mvp-smoke`. (Evidence: `.git/refs/heads/feat/mvp-smoke#L1`)

## Phase-0 Source of Truth

All Phase-0 product behavior, scope, constraints, and definitions are specified in the documents under `/docs`.

If any other document in the repository conflicts with `/docs`, the `/docs` specifications take precedence.

All future implementation work (including AI-generated changes) must treat `/docs` as the authoritative source for Phase-0.

## Definition, Goals, Non-Goals
- Definition: Buff is a modular crypto trading system intended for real personal use with real money in the future. (Evidence: `README.md#L6-L6`)
- Phase-0 product scope is a TradingView-like strategy analysis lab with a read-only UI (no buy/sell, no broker connections, no live execution controls). (Evidence: `docs/PRODUCT_SPEC.md#L1-L5`, `README.md#L6-L8`)
- Strategy invention is disallowed; users define indicators/strategies and the system only executes registered, approved strategies through a controlled pipeline. (Evidence: `README.md#L9-L10`)
- Goals: user-defined indicators/strategies, TradingView-like strategy analysis lab (chart-first, visual signals/trades/outcomes), read-only UI (no buy/sell/broker/live controls), menu-based strategy selection (no invention), deterministic/auditable pipeline, canonical 1m ingest with deterministic resampling. (Evidence: `PROJECT_SCOPE.md#L3-L9`)
- Non-goals: price prediction/forecasting, autonomous strategy generation by AI/LLMs (chatbot provides templates based on user-defined rules), direct UI-triggered order placement or live execution controls, broker connections or live trading controls in UI, multi-tenant SaaS or hosted user accounts (v1), hidden execution logic, signal selling/trading advice, live trading (out of Phase-0 product scope; future only), guaranteed profit claims. (Evidence: `PROJECT_SCOPE.md#L11-L17`, `README.md#L30-L36`)

## Safety Principles + Invariants
- Fail-closed everywhere: missing/invalid inputs block execution. (Evidence: `README.md#L14-L14`)
- Risk is a hard veto layer. (Evidence: `README.md#L15-L15`)
- UI and chatbot are read-only for execution; they cannot place orders. (Evidence: `README.md#L16-L16`)
- Execution runs independently from UI and requires explicit arming in the control plane. (Evidence: `README.md#L17-L17`)
- Full audit trail for every decision and order action. (Evidence: `README.md#L18-L18`)
- Canonical market data timeframe is 1m; higher timeframes are deterministic resamples. (Evidence: `README.md#L19-L19`)
- Invariants: deterministic outputs for a given snapshot/config, UTC timestamps, stable ordering/deterministic aggregation, no hidden state mutation, reproducible outputs across reruns. (Evidence: `README.md#L23-L28`)

## Planes + Boundaries
- Planes: Core/Data (data ingest/validate/store, features, risk, selector, execution), Control (arming/disarming, approvals/limits, kill switch), Interface (UI + Chatbot, read-only for execution). (Evidence: `ARCHITECTURE.md#L5-L20`)
- Separation of planes: sandbox authoring (no live execution), control plane (arming/approvals/kill switch), execution plane (broker interaction, risk-locked order flow). (Evidence: `PROJECT_SCOPE.md#L18-L20`)
- Boundary: UI/chatbot are interface-only and cannot place orders directly; execution runs independently from UI; risk can veto everything. (Evidence: `PROJECT_SCOPE.md#L22-L22`, `ARCHITECTURE.md#L22-L25`)
- Phase-0 product scope is read-only; broker/execution integrations are out of scope. (Evidence: `PROJECT_SCOPE.md#L25-L26`)

## Data Timeframes + Resampling
- Base timeframe is 1m ingest; all higher intervals are deterministic resamples from 1m. (Evidence: `docs/data_timeframes.md#L3-L10`)
- Supported timeframes: fixed-duration `5m, 15m, 30m, 1h, 2h, 4h, 1d, 1w, 2w` and calendar-based `1M, 3M, 6M, 1Y`. (Evidence: `docs/data_timeframes.md#L12-L16`)
- Input schema for resampling requires `ts, open, high, low, close, volume`; input is strictly monotonic by `ts` with no duplicate timestamps. (Evidence: `docs/resampling.md#L7-L13`)
- Window alignment: UTC epoch boundaries, left-closed/right-open windows, timestamped by window start. (Evidence: `docs/resampling.md#L17-L19`)
- Aggregation rules per window: open=first, high=max, low=min, close=last, volume=sum. (Evidence: `docs/resampling.md#L27-L32`)
- Completeness rule: incomplete windows are dropped; a window is complete only with exactly `timeframe_seconds / 60` one-minute bars. (Evidence: `docs/resampling.md#L34-L37`)
- Determinism: identical input yields byte-for-byte identical output with stable ordering and no randomness. (Evidence: `docs/resampling.md#L41-L45`)

## MVP v0 (M1 + M3 Smoke Test)
- MVP v0 is the MVP Smoke Test (M1 + M3): deterministic ingest -> validation -> reproducibility check -> feature build (no execution logic). (Evidence: `README.md#L70-L72`)
- M1 artifacts: `data/ohlcv_1m/{SYMBOL}.parquet` and `.tmp_report/data_quality.json`. (Evidence: `docs/data_pipeline.md#L14-L17`)
- M1 invariants: timeframe fixed to 1m, UTC timestamps aligned to minute boundaries, strict validation, deterministic storage. (Evidence: `docs/data_pipeline.md#L19-L24`)
- M1 OHLCV parquet schema columns: `ts, open, high, low, close, volume`. (Evidence: `docs/artifacts.md#L5-L12`)
- M3 artifact: `features/market_state.parquet`. (Evidence: `README.md#L64-L68`)
- M3 metadata is stored next to the parquet as `market_state.meta.json`. (Evidence: `docs/feature-contract.md#L69-L80`)

## Risk Policy Contract + Schema
- Risk policy provides a deterministic, explainable permission-to-trade state (green/yellow/red) and is permission-only (no direction prediction, no strategy selection). (Evidence: `docs/RISK_POLICY.md#L3-L5`)
- States and sizing: green=1.0, yellow=0.5, red=0.0. (Evidence: `docs/RISK_POLICY.md#L7-L10`)
- Rule summary: high severity events within the window or cooldown -> red; medium severity events within the window -> yellow; otherwise green; low severity events do not change state. (Evidence: `docs/RISK_POLICY.md#L25-L30`)
- Explainability outputs include reasons and event_ids. (Evidence: `docs/RISK_POLICY.md#L32-L35`)
- Risk permission outputs include risk_state, permission, recommended_scale, reasons, metrics. (Evidence: `docs/RISK_POLICY.md#L43-L48`)
- Risk report schema required fields: risk_report_version, risk_state, permission, recommended_scale, reasons, thresholds, metrics, evaluated_at. (Evidence: `schemas/risk_report.schema.json#L5-L13`)

## Control Plane (arming + kill switch)
- Execution is gated by an explicit control plane; arming with approved inputs is required before paper execution; a kill switch always disarms. (Evidence: `README.md#L142-L143`)
- Control plane responsibilities include arming/disarming, approvals/limits, and kill switch. (Evidence: `ARCHITECTURE.md#L12-L15`)
- Kill switch blocks all new orders immediately; API/network failures and missing/invalid inputs block execution. (Evidence: `EXECUTION_SAFETY.md#L27-L33`)

## Decision Records
- Paper execution writes `workspaces/<run_id>/decision_records.jsonl`; each record is validated against `DECISION_RECORD_SCHEMA.md` and `src/decision_records/schema.py`. (Evidence: `README.md#L154-L158`)
- Execution decision record required fields include record_version, decision_id, timestamp, event_id, intent_id, strategy_id, risk_state, permission, action, reason, data_snapshot_hash, feature_snapshot_hash, execution. (Evidence: `DECISION_RECORD_SCHEMA.md#L5-L21`)
- M7 decision record required fields include decision_id, ts_utc, symbol, timeframe, code_version, run_context, artifacts, inputs, selection, outcome, hashes. (Evidence: `docs/DECISION_RECORD.md#L7-L42`)
- Schema versioning: MAJOR=breaking, MINOR=backward-compatible additive, PATCH=clarifications/no shape change; readers ignore unknown fields; writers emit required fields; MINOR additions are optional. (Evidence: `docs/DECISION_RECORD.md#L46-L57`)
- Corruption handling: report generation fails closed on invalid JSON lines; replay loading skips invalid lines and non-zero error count indicates corruption; corrupted runs should be regenerated or discarded. (Evidence: `docs/DECISION_RECORD.md#L104-L110`)
- Migration rule for empty strategy_id: if empty string and `strategy.name` + `strategy.version` exist, set `selection.strategy_id="{name}@{version}"`; if empty string and strategy fields missing, migration fails. (Evidence: `docs/DECISION_RECORD.md#L123-L131`)

## Snapshots + Replay
- Snapshot format fields: snapshot_version, decision_id, symbol, timeframe, market_data, features, risk_inputs, config, selector_inputs, snapshot_hash. (Evidence: `docs/REPLAY.md#L7-L18`)
- snapshot_hash is SHA256 of canonical JSON with snapshot_hash omitted; hash format is lowercase hex with no prefix. (Evidence: `docs/REPLAY.md#L18-L23`)
- Canonical JSON rules: UTF-8 encoding, sorted keys, no whitespace; implemented by `canonical_json_bytes`. (Evidence: `src/audit/canonical_json.py#L28-L64`)
- Snapshot hash computation uses canonical JSON over the payload without snapshot_hash; snapshot_hash must match computed value or validation fails. (Evidence: `src/audit/snapshot.py#L73-L94`)
- Snapshot artifacts are content-addressed as `artifacts/snapshots/snapshot_<hash>.json`; `snapshot_ref` uses the computed hash in the filename. (Evidence: `docs/REPLAY.md#L20-L21`, `src/audit/snapshot.py#L108-L111`)
- Replay equivalence compares core payloads and supports strict-core/strict-full modes. (Evidence: `docs/REPLAY.md#L27-L45`)
- make_snapshot `--out` is a directory; the snapshot file is written inside it and the created path is printed to stdout. (Evidence: `docs/REPLAY.md#L55-L63`)
- Replay output `--out` is directory-only; replay files are written as `replay_<decision_id>.json` inside the directory; passing a file path is an error. (Evidence: `docs/REPLAY.md#L79-L82`, `src/audit/replay.py#L479-L490`)

## CLI Entrypoints
- M1 ingest: `python -m src.data.ingest --symbols BTCUSDT ETHUSDT --since 2024-01-01T00:00:00Z --end 2024-01-03T00:00:00Z --out data --report .tmp_report/data_quality.json`. (Evidence: `docs/data_pipeline.md#L10-L12`)
- M3 features: `python -m src.features.cli --input data/clean/BTC_USDT_1h.parquet --output features/market_state.parquet`. (Evidence: `README.md#L64-L68`)
- MVP smoke test: `python -m src.tools.mvp_smoke --symbols BTCUSDT ETHUSDT --timeframe 1h --since 2023-01-01 --until 2023-02-01`. (Evidence: `README.md#L76-L78`)
- M4 risk timeline: `python -m src.risk.cli --events tests/fixtures/risk_events.json --start 2026-01-10T08:00:00Z --end 2026-01-10T20:00:00Z --out reports/risk_timeline.json`. (Evidence: `README.md#L91-L95`)
- M7 audit tooling: `python -m src.audit.record_decision --input tests/fixtures/decision_payload.json --out artifacts/decisions`; `python -m src.audit.make_snapshot --input tests/fixtures/snapshot_payload.json --out artifacts/snapshots`; `python -m src.audit.replay --decision <decision_path.json> --snapshot <snapshot_path.json> --strict`. (Evidence: `README.md#L169-L173`)
- Decision record migration: `python -m src.audit.migrate_records --in <path> --out artifacts/migrated`. (Evidence: `README.md#L180-L181`)

## Quality Gates
- Quality gates: `ruff check .`, `pytest -q`, `ruff format --check .`. (Evidence: `README.md#L125-L130`)

## Phase-0 Status

Phase-0 is complete and locked.

Product scope, UI behavior, extensibility rules, risk model, and AI assistant roles are frozen as specified under `/docs`.

All subsequent work must be treated as Phase-1+ implementation and MUST NOT redefine Phase-0 decisions.
