# Phase-6: Make Buff Actually Usable

## Purpose

Deliver a fully usable, end-to-end run creation workflow with durable storage, real data ingest, and a UI path to create and inspect runs while preserving safety and determinism.

## No-skip Rule (Strict Sequencing)

Stage N must meet its Definition of Done and pass its gates before Stage N+1 begins. No parallel execution across stages and no partial carryover of unfinished requirements.

## Stage 1: Real Run Builder

**Goal**: Generate new run artifacts end-to-end, register the run, and have the UI list and display it.

**Inputs**: Run config (strategy pack selection, timeframe, symbols), approved data source handle, run metadata.

**Outputs**: New run artifacts directory, registry entry, UI-visible run record.

**Definition of Done**:
- A single command can create a new run with deterministic artifacts.
- Run is registered in the run index/registry with a stable ID.
- `/runs/<id>` loads and renders the new run without manual file copying.
- Artifacts pass schema validation (decision records, trades optional).
- Run builder writes a minimal manifest for reproducibility (config + inputs).

**Tests / Gates**:
```bash
python -m src.run.builder --config configs/run_demo.yml --runs-root runs
python -m src.cli validate-run --run-id <id> --workspaces runs
node apps/web/scripts/ui-smoke.mjs
```

**Notes**:
- Avoid inventing strategy logic; builder only orchestrates approved components.
- Ensure deterministic IDs and consistent directory layout.
- Keep artifacts read-only in UI and API layers.

## Stage 2: Durable Storage

**Goal**: Make run storage crash-safe, restart-safe, and authoritative via `RUNS_ROOT`.

**Inputs**: `RUNS_ROOT` env var, run manifest, registry/index definitions.

**Outputs**: Crash-safe run index/registry, restart persistence, durable run metadata.

**Definition of Done**:
- `RUNS_ROOT` is the single authoritative root for all runs.
- Registry/index updates are atomic and recoverable after crash.
- Restarting API/UI preserves run visibility and metadata.
- Registry includes minimal metadata for listing and filtering.
- Backward-compatible support for existing Phase-1 artifacts (read-only).

**Tests / Gates**:
```bash
python -m src.workspaces.cli index --workspaces %RUNS_ROOT%
python -m src.cli list-runs --workspaces %RUNS_ROOT%
pytest -q tests/phase6/test_run_registry.py
```

**Notes**:
- Define write-path locking and file-rename semantics.
- Avoid implicit defaults that could hide corrupt runs.
- Explicitly document migration path from `artifacts/`.

## Stage 3: Real Data Ingestion

**Goal**: CSV import MVP with sanity checks and reproducibility guarantees.

**Inputs**: User-provided CSV (OHLCV + timestamp), ingest config, timeframe.

**Outputs**: Canonical 1m ingest artifacts, resampled outputs, quality report.

**Definition of Done**:
- CSV import produces canonical 1m data with validation rules enforced.
- Sanity checks fail-closed (missing columns, timestamp gaps, invalid rows).
- Deterministic resample to higher timeframes.
- Reproducible outputs for fixed windows.
- Ingest outputs are recorded in the run manifest.

**Tests / Gates**:
```bash
python -m src.ingest.csv --input data/sample.csv --out %RUNS_ROOT%\<id>
python -m src.tools.mvp_smoke --symbols BTCUSDT --timeframe 1h --since 2023-01-01 --until 2023-02-01
pytest -q tests/phase6/test_ingest_csv.py
```

**Notes**:
- Define strict CSV schema and timestamp normalization (UTC).
- Reject ambiguous timezones and mixed timeframes.
- Guard against partial rows and unordered timestamps.

## Stage 4: Usable UX

**Goal**: Add `/runs/new` to create a run from the UI with safe defaults.

**Inputs**: UI form inputs, validated run config, available datasets.

**Outputs**: Created run ID, immediate redirect to `/runs/<id>`.

**Definition of Done**:
- UI form enforces required inputs and prevents invalid configs.
- Run creation uses the Stage-1 builder and Stage-2 registry.
- User receives deterministic, reproducible run ID in the UI.
- Failure states are explicit and non-destructive.
- `/runs/new` is behind a safe feature flag (off by default).

**Tests / Gates**:
```bash
node apps/web/scripts/ui-smoke.mjs
pytest -q tests/phase6/test_runs_new_ui.py
```

**Notes**:
- Keep UI read-only for execution controls; only run creation is allowed.
- Avoid blocking UI on long-running ingest; use background job + status.
- Enforce server-side validation even if UI validates.

## Stage 5: Reliability & Safety

**Goal**: Harden the system with health checks, limits, kill switch, and structured logs.

**Inputs**: Runtime health metrics, rate limits, control plane configuration.

**Outputs**: Safe runtime behavior, observable failures, enforced limits.

**Definition of Done**:
- Health endpoint includes run builder and registry checks.
- Configurable limits on run creation, ingest size, and concurrency.
- Kill switch disables new runs and ingest immediately.
- Structured logs for run creation, ingestion, and registry updates.
- Reliability regressions blocked by CI gate.

**Tests / Gates**:
```bash
python -m tools.release_preflight --timeout-seconds 900
python -m tools.release_gate --strict --timeout-seconds 900
pytest -q tests/phase6/test_safety_limits.py
```

**Notes**:
- Define safe defaults and explicit overrides.
- Ensure kill switch is fail-closed and audited.
- Avoid silent retries that could corrupt run state.
