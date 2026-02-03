# Buff
[![CI](https://github.com/Buff-Trading-AI/Buff/actions/workflows/ci.yml/badge.svg)](https://github.com/Buff-Trading-AI/Buff/actions/workflows/ci.yml)

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
- Canonical market data timeframe is 1m; all higher timeframes are deterministic resamples.

## Invariants & Non-goals

Invariants:
- Deterministic outputs for a given snapshot and configuration.
- UTC time basis for timestamps.
- Stable ordering for records and deterministic aggregation.
- No hidden state mutation; inputs are explicit and versioned.
- Reproducible outputs across reruns.

Non-goals:
- Price prediction / forecasting ("no prediction").
- Signal selling or trading advice.
- Live trading.
- Guaranteed profit claims.

Boundary:
- UI and chatbot are strictly read-only; no execution is triggered from UI/chatbot.

## Data Timeframe Canonicalization

- Ingest/base timeframe is **1m**; higher timeframes are derived deterministically.
- See `docs/data_timeframes.md` and `docs/PROJECT_SPEC.md` for the authoritative rules.

## Documentation

- `docs/PROJECT_SPEC.md` (single source of truth)
- `docs/data_timeframes.md` (canonical 1m + resampling rules)
- `ARCHITECTURE.md`
- `PROJECT_SCOPE.md`
- `EXECUTION_SAFETY.md`

## Quickstart

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Generate local artifacts

Generate the M3 market state artifact:

```bash
python -m src.features.cli --input data/clean/BTC_USDT_1h.parquet --output features/market_state.parquet
```

## MVP Smoke Test (M1 + M3)

Runs deterministic ingest -> validation -> reproducibility check -> feature build (no execution logic).

Fixed time window (recommended for reproducibility):

```bash
python -m src.tools.mvp_smoke --symbols BTCUSDT ETHUSDT --timeframe 1h --since 2023-01-01 --until 2023-02-01
```

Rolling end time (defaults to last completed bar):

```bash
python -m src.tools.mvp_smoke --symbols BTCUSDT ETHUSDT --timeframe 1h --since 2023-01-01
```

Guarantees:
- Canonical 1m ingest, then deterministic resample to the requested timeframe.
- Reproducibility is guaranteed for the same fixed time window; without --until, the end time is derived from the last completed bar.
- Deterministic M3 feature bundle build for BTCUSDT.

Generate the M4 risk timeline artifact:

```bash
python -m src.risk.cli --events tests/fixtures/risk_events.json --start 2026-01-10T08:00:00Z --end 2026-01-10T20:00:00Z --out reports/risk_timeline.json
```

## Dependency Locking

Install uv (Linux/macOS):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Regenerate lockfile:

```bash
uv lock --upgrade
```

Frozen install (CI-compatible):

```bash
uv sync --frozen --extra dev
```

Run gates locally:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
```

## Quality Gates

```bash
ruff check .
pytest -q
ruff format --check .
```

## Governance / Safety

See GITHUB_SETTINGS_CHECKLIST.md for required GitHub UI settings.

See SECURITY.md for disclosure and secrets policy. The project forbids prediction or
signal logic and requires deterministic, auditable changes.

## Control Plane (arming / kill switch)

Execution is gated by an explicit control plane. You must arm the system with
approved inputs before any paper execution can run. A kill switch always disarms.

Example (code):

<!-- NOTE (underspecified): Run context (working directory, PYTHONPATH) for these imports is not specified. -->

```python
from control_plane.control import arm
from control_plane.state import ControlConfig, Environment

state = arm(ControlConfig(environment=Environment.PAPER, required_approvals={"ok"}), approvals=["ok"])
```

## Decision Record Schema v1.0

<!-- NOTE (underspecified): Relationship between this schema and the M7 schema in docs/DECISION_RECORD.md (and DECISION_RECORD_SCHEMA.md) is not defined here. -->

Paper execution writes one file per run, `workspaces/<run_id>/decision_records.jsonl`, with one
JSON object per line; each record includes the required fields: schema_version, run_id,
timestamp_utc, environment, control_status, strategy{name,version}, risk_status, execution_status,
reason (for BLOCKED/ERROR), inputs_digest, artifact_paths.

run_id is sanitized to `[A-Za-z0-9_-]` and records are fail-closed if validation fails.
Control plane state loading defaults to DISARMED if the state file is missing or corrupt.

See `docs/DECISION_RECORD.md` for the full schema, replay semantics, and schema versioning &
compatibility rules.

## Replay & Reproducibility (M7)

Deterministic decision records and snapshots enable full replay in isolation from mutable state.

Commands:

```bash
python -m src.audit.record_decision --input tests/fixtures/decision_payload.json --out artifacts/decisions
python -m src.audit.make_snapshot --input tests/fixtures/snapshot_payload.json --out artifacts/snapshots
python -m src.audit.replay --decision <decision_path.json> --snapshot <snapshot_path.json> --strict
```

Expected outputs:

- `REPLAY_OK strict-core` on success when using `--strict`; `REPLAY_OK non-strict` when not using `--strict`.
- `REPLAY_MISMATCH` with a structured diff on mismatch

Legacy decision records can be migrated with:
`python -m src.audit.migrate_records --in <path> --out artifacts/migrated`

- Verification report: `reports/m7_verification_report.md`
  <!-- NOTE (underspecified): Whether this file is generated by a command or a checked-in artifact is not specified. -->

## End-to-End Flow

Data -> Features -> Risk -> Strategy Selection -> Execution

- Data: canonical 1m ingest; higher timeframes derived deterministically; quality reports
- Features: preset indicators and user-approved indicators
- Risk: permission layer (GREEN/YELLOW/RED)
- Strategy Selection: picks only from registered strategies
- Execution: paper trading first, staged live later

## Done v1.0

- Stable paper trading
- Full audit trail (`workspaces/<run_id>/decision_records.jsonl`)
- Deterministic, reproducible runs

## Modes

Manual mode is a sandbox with no effect on the system. It writes only to workspaces/.

Example:

```bash
python -m src.manual.run_manual --workspace demo --symbol BTCUSDT --timeframe 1m
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

## Report Generator (M4.3)

Generates deterministic audit reports from decision logs.

- Reads: `workspaces/<run_id>/decision_records.jsonl`
- Writes: `workspaces/<run_id>/report.md` and `workspaces/<run_id>/report_summary.json`

Example:

```bash
python -m src.reports.cli --run-id demo
python -m src.reports.cli --run-id demo --workspace workspaces --last-n 25
```

## Workspace Index (M4.4)

Builds a deterministic index of audit runs in `workspaces/`.

- Outputs: `workspaces/index.json` and `workspaces/index.md`

Commands:

```bash
python -m src.workspaces.cli list --workspaces workspaces
python -m src.workspaces.cli show --run-id <id> --workspaces workspaces
python -m src.workspaces.cli index --workspaces workspaces
```

## Buff Audit CLI (M4.6)

Unified read-only entrypoint for audit workflows (no trading or strategy logic).

Commands:

```bash
python -m src.cli index --workspaces workspaces
python -m src.cli list-runs --workspaces workspaces
python -m src.cli show --run-id <id> --workspaces workspaces
python -m src.cli report --run-id <id> --workspaces workspaces --last-n 50
python -m src.cli validate-run --run-id <id> --workspaces workspaces
```

## Chatbot Read-Only Artifact Navigator (M4.5)

Provides deterministic, read-only lookup of audit artifacts for a given run.
No interpretation or decision-making is performed.

Commands:

```bash
python -m src.chatbot.cli list-runs
python -m src.chatbot.cli show-run --run-id <id>
```
