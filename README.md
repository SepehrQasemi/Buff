# Buff
[![CI](https://github.com/Buff-Trading-AI/Buff/actions/workflows/ci.yml/badge.svg)](https://github.com/Buff-Trading-AI/Buff/actions/workflows/ci.yml)
[![CodeQL](https://github.com/Buff-Trading-AI/Buff/actions/workflows/codeql.yml/badge.svg)](https://github.com/Buff-Trading-AI/Buff/actions/workflows/codeql.yml)


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

See GITHUB_SETTINGS_CHECKLIST.md for required GitHub UI settings.

See SECURITY.md for disclosure and secrets policy. The project forbids prediction or
signal logic and requires deterministic, auditable changes.

## Control Plane (arming / kill switch)

Execution is gated by an explicit control plane. You must arm the system with
approved inputs before any paper execution can run. A kill switch always disarms.

Example (code):

```python
from control_plane.control import arm
from control_plane.state import ControlConfig, Environment

state = arm(ControlConfig(environment=Environment.PAPER, required_approvals={"ok"}), approvals=["ok"])
```

## Decision Record Schema v1.0

Paper execution writes `workspaces/<run_id>/decision_records.jsonl` with required fields:
schema_version, run_id, timestamp_utc, environment, control_status, strategy{name,version},
risk_status, execution_status, reason (for BLOCKED/ERROR), inputs_digest, artifact_paths.

run_id is sanitized to `[A-Za-z0-9_-]` and records are fail-closed if validation fails.
Control state loading defaults to DISARMED if the state file is missing or corrupt.

## Replay & Reproducibility (M7)

Deterministic decision records and snapshots enable full replay in isolation from mutable state.

Commands:

```bash
python -m src.audit.record_decision --input tests/fixtures/decision_payload.json --out artifacts/decisions
python -m src.audit.make_snapshot --input tests/fixtures/snapshot_payload.json --out artifacts/snapshots
python -m src.audit.replay --decision <decision_path.json> --snapshot <snapshot_path.json> --strict
```

Expected outputs:

- `REPLAY_OK strict-core` on success
- `REPLAY_MISMATCH` with a structured diff on mismatch

Legacy decision records can be migrated with:
`python -m src.audit.migrate_records --in <path> --out artifacts/migrated`

- Verification report: `reports/m7_verification_report.md`

## End-to-End Flow

Data -> Features -> Risk -> Strategy Selection -> Execution

- Data: deterministic OHLCV ingest and quality reports
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
