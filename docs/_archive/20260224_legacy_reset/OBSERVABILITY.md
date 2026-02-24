ARCHIVED — NOT AUTHORITATIVE
Superseded by new documentation reset 2026-02-24.
Do not rely on this file for current stage or product direction.

# OBSERVABILITY

## Purpose
This document is the canonical location for S0 -> S1 gate evidence on observability and run intelligence surfaces.

## API Surface
- `GET /api/v1/ready` checks `RUNS_ROOT` readiness and registry accessibility. On success it returns `status=ready` and `checks.runs_root` plus `checks.registry`.
- `GET /api/v1/runs/{run_id}/metrics` loads `metrics.json` for a run and returns `metrics_missing` (`404`) or `metrics_invalid` (`422`) on failure.
- `GET /api/v1/runs/{run_id}/diagnostics` returns run health signals: `status`, `health`, `missing_artifacts`, `invalid_artifacts`, `checks`, `artifacts_present`, and `last_verified_at`.

## Registry Index
- Run index file: `RUNS_ROOT/index.json`.
- Registry lock file: `RUNS_ROOT/.registry.lock`.
- API list/read paths reconcile registry under lock before serving run listings/details.
- Registry writes are atomic (`index.json.tmp` then `os.replace`) with directory fsync.

## Failure Modes
- Readiness: `RUNS_ROOT_UNSET`, `RUNS_ROOT_MISSING`, `RUNS_ROOT_INVALID`, `RUNS_ROOT_NOT_WRITABLE`.
- Registry: `REGISTRY_LOCK_TIMEOUT`, `REGISTRY_WRITE_FAILED`.
- Run reads: `RUN_NOT_FOUND`, `invalid_run_id`, `metrics_missing`, `metrics_invalid`.

## Code References
- `apps/api/main.py`
- `apps/api/artifacts.py`
- `apps/api/phase6/registry.py`
- `apps/api/phase6/run_builder.py`
- `docs/03_CONTRACTS_AND_SCHEMAS.md`
