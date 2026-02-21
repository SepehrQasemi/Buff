# Runbook And Dev Workflow

Canonical operational guide for core local run, verification, and recovery flows. These core operational command strings are maintained here as the single source.

## Table Of Contents
- [Quickstart](#quickstart)
- [Verification Gates](#verification-gates)
- [Service Lifecycle](#service-lifecycle)
- [One-command Local Run (Compose)](#one-command-local-run-compose)
- [Export Report Workflow](#export-report-workflow)
- [Long-Run Harness](#long-run-harness)
- [Chatbot Operations](#chatbot-operations)
- [CI Backup Operations](#ci-backup-operations)
- [Data Pipeline Operations](#data-pipeline-operations)
- [Replay Operations](#replay-operations)
- [Phase6 Doc Ops](#phase6-doc-ops)
- [Troubleshooting Matrix](#troubleshooting-matrix)
- [Pre-PR Checklist](#pre-pr-checklist)
- [References](#references)

## Quickstart
Prerequisites: Python 3.10+, Node.js + npm.

```bash
python -m pip install -e ".[dev]"
npm --prefix apps/web install
```

Then run the Phase-1 real-smoke gate from [Verification Gates](#verification-gates).

## Verification Gates
Use these canonical gate commands:

```bash
python scripts/verify_phase1.py --with-services [--real-smoke]
python -m tools.release_preflight --timeout-seconds 900
python -m tools.release_gate --strict --timeout-seconds 900
```

### Real Smoke User Context
Phase-1 real-smoke runs in multi-user mode; API requests require `X-Buff-User`. Set `BUFF_DEFAULT_USER` so verification uses a deterministic default user context.

```powershell
$env:BUFF_DEFAULT_USER='phase1_smoke_user'; python scripts/verify_phase1.py --with-services --real-smoke
```

```bash
BUFF_DEFAULT_USER=phase1_smoke_user python scripts/verify_phase1.py --with-services --real-smoke
```

Contract reference for fail-closed errors and required artifacts:
- [03_CONTRACTS_AND_SCHEMAS.md#canonical-error-schema](./03_CONTRACTS_AND_SCHEMAS.md#canonical-error-schema)
- [03_CONTRACTS_AND_SCHEMAS.md#artifact-contract-matrix](./03_CONTRACTS_AND_SCHEMAS.md#artifact-contract-matrix)

## Service Lifecycle
Start API + UI:

```bash
python scripts/dev_start.py
```

Stop services:

```bash
python scripts/stop_services.py
```

Port overrides before starting:
- PowerShell: set `$env:API_PORT` and `$env:UI_PORT`, then run the start command above.
- Bash: set `API_PORT` and `UI_PORT`, then run the start command above.

Operational defaults:
- `RUNS_ROOT` defaults to `.runs` under the repo when using `dev_start.py`.
- `DEMO_MODE=0` for local verification flows.
- UI remains read-only and artifact-driven.

Next.js lock recovery:
- Confirm no UI listener exists on `3000..3020`.
- Remove stale lock: `Remove-Item -Force .\apps\web\.next\dev\lock`

## One-command Local Run (Compose)
Use the canonical compose wrapper scripts:

```bash
scripts/dev_up.sh up
scripts/dev_up.sh logs
scripts/dev_up.sh down
scripts/dev_up.sh reset-runs
```

```powershell
.\scripts\dev_up.ps1 up
.\scripts\dev_up.ps1 logs
.\scripts\dev_up.ps1 down
.\scripts\dev_up.ps1 reset-runs
```

Notes:
- Compose uses repo-local deterministic run storage at `.runs_compose` by default (`RUNS_ROOT_HOST` override supported).
- `reset-runs` is scoped to `RUNS_ROOT_HOST` only and refuses unsafe paths.
- API readiness contract for compose healthcheck is `GET /api/v1/health/ready`.

## Export Report Workflow

```bash
python scripts/export_report.py --runs-root <RUNS_ROOT> --run-id <RUN_ID>
```

Expected outputs:
- `<RUNS_ROOT>/<RUN_ID>/report.md`
- Supporting artifacts remain under the same run directory.

## Long-Run Harness
Generate a large feed:

```bash
python -m src.paper.feed_generate --out runs/feeds/feed_500k.jsonl --rows 500000 --seed 42
```

Run the long harness (example: 6 hours):

```bash
python -m src.paper.cli_long_run --run-id longrun_001 --duration-seconds 21600 --restart-every-seconds 900 --rotate-every-records 50000 --replay-every-records 20000 --feed runs/feeds/feed_500k.jsonl
```

Generate an audit summary:

```bash
python -m src.audit.report_decisions --run-dir runs/longrun_001 --out runs/longrun_001/summary.json
```

Acceptance:
- `summary.json` exists.
- Replay verification counters for mismatched/hash_mismatch/errors are all `0`.

## Chatbot Operations
### Generate Daily Summary
Use this command to generate `reports/daily_summary.md` from chatbot reporting artifacts (replace `RUN_ID`):

```bash
python -c "from pathlib import Path; from chatbot import Chatbot, ChatbotConfig; run_id='RUN_ID'; cfg=ChatbotConfig(root_dir=Path('.'), trades_path=Path(f'workspaces/{run_id}/trades.parquet'), selector_trace_path=Path(f'workspaces/{run_id}/selector_trace.json'), risk_timeline_path=Path('reports/risk_timeline.json')); Path('reports/daily_summary.md').write_text(Chatbot(cfg).respond('daily summary'), encoding='utf-8')"
```

## CI Backup Operations
### Clouding Connectivity Check
Archived operator flow for listing Clouding servers:

```bash
export CLOUDING_APIKEY="..."
./scripts/clouding_list_servers.sh
```

### Clouding Power Cycle Check
Archived operator flow for unarchive/archive power actions:

```bash
export CLOUDING_APIKEY="..."
export SERVER_ID="..."
./scripts/clouding_power.sh unarchive
./scripts/clouding_power.sh archive
```

## Data Pipeline Operations
### Canonical 1m Ingest
Build canonical deterministic 1m OHLCV artifacts and a quality report:

```bash
python -m src.data.ingest --symbols BTCUSDT ETHUSDT --since 2024-01-01T00:00:00Z --end 2024-01-03T00:00:00Z --out data --report .tmp_report/data_quality.json
```

### Fundamental Risk CLI
Run the offline-first fundamental risk evaluator against fixture snapshots:

```bash
python -m src.risk_fundamental.cli --rules knowledge/fundamental_risk_rules.yaml --fixture tests/fixtures/fundamental_snapshots.json --at 2026-01-01T00:00:00Z
```

## Replay Operations
### Record Decision Payload
Record canonical decision artifacts and hashes:

```bash
python -m src.audit.record_decision --input tests/fixtures/decision_payload.json --out artifacts/decisions
```

### Create Snapshot
Create snapshot artifacts used by replay:

```bash
python -m src.audit.make_snapshot --input tests/fixtures/snapshot_payload.json --out artifacts/snapshots
```

### Replay Decision
Replay a decision in strict-core mode:

```bash
python -m src.audit.replay --decision <decision_path.json> --snapshot <snapshot_path.json> --strict
```

### Decision Record Migration Helper
Run structural migration for legacy decision records:

```bash
python -m src.audit.migrate_records --in tests/fixtures/legacy_records --out artifacts/migrated
```

## Phase6 Doc Ops
### Stage-5 Demo
Run the read-only Phase-6 demo with the built-in artifacts pack:

```bash
./scripts/dev-demo.sh
```

```powershell
.\scripts\dev-demo.ps1
```

### Phase6 Plugin Validation
Generate plugin validation artifacts:

```bash
python -m src.plugins.validate --out artifacts/plugin_validation
```

### Phase6 Plugin Test Check
Run plugin-focused test checks:

```bash
python -m pytest -q
```

## Troubleshooting Matrix
| Symptom | Likely Cause | Recovery |
| --- | --- | --- |
| API/UI bind fails | Port already in use | Stop conflicting process or set `API_PORT`/`UI_PORT`, then run the start command. |
| UI dev lock persists | Stale Next lock file | Remove lock only when no active listener exists on `3000..3020`. |
| `RUNS_ROOT_UNSET` or `RUNS_ROOT_MISSING` | Missing or invalid run root | Use start defaults or set `RUNS_ROOT` to an existing repo-local directory. |
| Missing panels or `metrics_missing` | Partial run artifacts | Recreate run and validate required files against contracts. |
| `DATA_INVALID` on run creation | CSV schema/timestamp issues | Ensure `timestamp, open, high, low, close, volume` with increasing timestamps and no gaps. |
| UI smoke env failure | Missing `API_BASE_URL`/`UI_BASE_URL` | Set both env vars or run verification gates as documented. |

## Pre-PR Checklist
- `python -m ruff format .`
- `python -m ruff check .`
- `python -m pytest -q`
- Run the strict release gate command from [Verification Gates](#verification-gates).
- Ensure `git status -sb` is clean.

## References
- [FIRST_RUN.md](./FIRST_RUN.md)
- [RELEASE_PRECHECK.md](./RELEASE_PRECHECK.md)
- [RELEASE_GATE.md](./RELEASE_GATE.md)
- [long_run_playbook.md](./long_run_playbook.md)
- [VERIFY_PHASE1_DIAGNOSIS.md](./VERIFY_PHASE1_DIAGNOSIS.md)
