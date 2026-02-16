# Runbook And Dev Workflow

## Table Of Contents
- [Core Commands](#core-commands)
- [Troubleshooting Matrix](#troubleshooting-matrix)
- [Pre-PR Checklist](#pre-pr-checklist)
- [References](#references)

## Core Commands
Start local services:

```bash
python scripts/dev_start.py
```

Verify layer-1 behavior:

```bash
python scripts/verify_phase1.py --with-services
python scripts/verify_phase1.py --with-services --real-smoke
```

Stop services:

```bash
python scripts/stop_services.py
```

Export run report:

```bash
python scripts/export_report.py --runs-root <RUNS_ROOT> --run-id <RUN_ID>
```

## Troubleshooting Matrix
| Symptom | Likely Cause | Action |
| --- | --- | --- |
| API or UI port bind failure | Port already in use | Set `API_PORT` / `UI_PORT`, then restart |
| UI dev lock issues | Stale Next lock | Remove `apps/web/.next/dev/lock` when no UI listener exists |
| `RUNS_ROOT_UNSET` | Missing environment variable | Set repo-local `RUNS_ROOT` and restart |
| Missing artifacts in UI | Incomplete run artifacts | Recreate run and verify contract-required files |
| Smoke test fails | Services not ready or wrong base URLs | Re-run verify scripts and confirm env vars |

## Pre-PR Checklist
- `python -m ruff format .`
- `python -m ruff check .`
- `python -m pytest -q`
- `python -m tools.release_gate --strict --timeout-seconds 900`

## References
- First run guide: [FIRST_RUN.md](./FIRST_RUN.md)
- Phase-1 diagnosis notes: [VERIFY_PHASE1_DIAGNOSIS.md](./VERIFY_PHASE1_DIAGNOSIS.md)
- Release gate docs: [RELEASE_PRECHECK.md](./RELEASE_PRECHECK.md), [RELEASE_GATE.md](./RELEASE_GATE.md)
