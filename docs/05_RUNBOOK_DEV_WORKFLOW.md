# Runbook And Dev Workflow

Canonical operational guide for local run, verification, and recovery flows. All operational command strings live in this file only.

## Table Of Contents
- [Quickstart](#quickstart)
- [Verification Gates](#verification-gates)
- [Service Lifecycle](#service-lifecycle)
- [Export Report Workflow](#export-report-workflow)
- [Long-Run Harness](#long-run-harness)
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

Contract reference for fail-closed errors and required artifacts:
- [03_CONTRACTS_AND_SCHEMAS.md#error-schema](./03_CONTRACTS_AND_SCHEMAS.md#error-schema)
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
