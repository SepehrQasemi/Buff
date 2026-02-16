# Runbook And Dev Workflow

Canonical operational guide for local run/verify/recover workflows. This is the single source of truth for developer commands.

## Table Of Contents
- [Quickstart](#quickstart)
- [Verification Gates](#verification-gates)
- [Service Lifecycle](#service-lifecycle)
- [Export Report Workflow](#export-report-workflow)
- [Long-Run Harness](#long-run-harness)
- [Troubleshooting Matrix](#troubleshooting-matrix)
- [Before Opening A PR](#before-opening-a-pr)
- [References](#references)

## Quickstart
Prerequisites: Python 3.10+, Node.js + npm.

```bash
python -m pip install -e ".[dev]"
npm --prefix apps/web install
python scripts/verify_phase1.py --with-services --real-smoke
```

## Verification Gates
Phase-1 gate (service-backed):

```bash
python scripts/verify_phase1.py --with-services
python scripts/verify_phase1.py --with-services --real-smoke
```

Release gate (strict, fail-closed):

```bash
python -m tools.release_gate --strict --timeout-seconds 900
```

Release preflight (clean tree + ff-only sync + release gate):

```bash
python -m tools.release_preflight --timeout-seconds 900
```

Contract reference for fail-closed errors and required artifacts:
- [03_CONTRACTS_AND_SCHEMAS.md](./03_CONTRACTS_AND_SCHEMAS.md#error-schema)
- [03_CONTRACTS_AND_SCHEMAS.md](./03_CONTRACTS_AND_SCHEMAS.md#artifact-contract-matrix)

## Service Lifecycle
Start API + UI together:

```bash
python scripts/dev_start.py
```

Stop services:

```bash
python scripts/stop_services.py
```

Port overrides:
- PowerShell: `$env:API_PORT=8001; $env:UI_PORT=3001; python scripts/dev_start.py`
- Bash: `API_PORT=8001 UI_PORT=3001 python scripts/dev_start.py`

Operational defaults:
- `RUNS_ROOT` defaults to `.runs` under the repo when using `dev_start.py`.
- `DEMO_MODE=0` for local verification flows.
- UI remains read-only and artifact-driven.

Next.js lock recovery:
- Confirm no UI listener exists on `3000..3020`.
- Remove stale lock: `Remove-Item -Force .\apps\web\.next\dev\lock`

## Export Report Workflow
Generate a report from an existing run directory:

```bash
python scripts/export_report.py --runs-root <RUNS_ROOT> --run-id <RUN_ID>
```

Expected output:
- `<RUNS_ROOT>/<RUN_ID>/report.md`

## Long-Run Harness
Generate large feed data:

```bash
python -m src.paper.feed_generate --out runs/feeds/feed_500k.jsonl --rows 500000 --seed 42
```

Run long paper harness (example: 6 hours):

```bash
python -m src.paper.cli_long_run --run-id longrun_001 --duration-seconds 21600 --restart-every-seconds 900 --rotate-every-records 50000 --replay-every-records 20000 --feed runs/feeds/feed_500k.jsonl
```

Generate audit summary:

```bash
python -m src.audit.report_decisions --run-dir runs/longrun_001 --out runs/longrun_001/summary.json
```

Acceptance criteria:
- `summary.json` exists.
- `replay_verification.mismatched == 0`
- `replay_verification.hash_mismatch == 0`
- `replay_verification.errors == 0`

## Troubleshooting Matrix
| Symptom | Likely Cause | Recovery |
| --- | --- | --- |
| API/UI fails to bind | Port already in use | Stop conflicting process or set `API_PORT` / `UI_PORT` and rerun `dev_start.py`. |
| `apps/web/.next/dev/lock` blocks startup | Stale Next lock file | Remove lock only when no UI listener is active on `3000..3020`. |
| `RUNS_ROOT_UNSET` or `RUNS_ROOT_MISSING` | Missing or invalid run root | Use `dev_start.py` defaults or set `RUNS_ROOT` to an existing repo-local directory. |
| `RUN_NOT_FOUND`, `metrics_missing`, missing panels | Missing artifacts for run | Recreate run from valid CSV; verify required artifacts in contract matrix. |
| `DATA_INVALID` while creating a run | CSV schema/timestamp issues | Include `timestamp, open, high, low, close, volume`; ensure increasing timestamps and no gaps. |
| UI smoke fails for missing API/UI base env | `API_BASE_URL`/`UI_BASE_URL` unset | Use verify command above or set both env vars before `node apps/web/scripts/ui-smoke.mjs`. |
| `verify_phase1` appears non-zero in PowerShell pipeline | Pipeline exit-code masking | Run without piping and check `$LASTEXITCODE` directly. See archived diagnosis notes. |

## Before Opening A PR
Run from repo root:

```bash
python -m ruff format .
python -m ruff check .
python -m pytest -q
python -m tools.release_gate --strict --timeout-seconds 900
```

Verify:
- `git status -sb` is clean.
- No conflicting local services are still listening on UI/API ports.

## References
- [FIRST_RUN.md](./FIRST_RUN.md) (pointer to this runbook)
- [RELEASE_PRECHECK.md](./RELEASE_PRECHECK.md) (pointer to verification gates)
- [RELEASE_GATE.md](./RELEASE_GATE.md) (pointer to verification gates)
- [long_run_playbook.md](./long_run_playbook.md) (pointer to long-run appendix workflows)
- [VERIFY_PHASE1_DIAGNOSIS.md](./VERIFY_PHASE1_DIAGNOSIS.md) (pointer to incident archive)
