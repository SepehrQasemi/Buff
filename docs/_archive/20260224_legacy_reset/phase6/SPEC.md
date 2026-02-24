ARCHIVED — NOT AUTHORITATIVE
Superseded by new documentation reset 2026-02-24.
Do not rely on this file for current stage or product direction.

# Phase-6 Execution Spec

## Stage Authority
Global stage status, Definition of Done, and transition gating are authoritative in `../PROJECT_STATE.md`.
This spec is an implementation plan for Phase-6 scope and must remain aligned with that authority.

## Problem Statement
Phase-1 relies on fixture artifacts and manual file placement. Users cannot create new runs from real inputs or persist them safely. This is a demo capability, not a usable product.

## Target Personas
- Solo builder or quant who wants local, deterministic analysis on their own data.
- Technical user who can provide CSV data and expects reproducible artifacts.
- Reviewer who needs to inspect runs via a read-only UI with traceable outputs.

## In-Scope
- Create runs from real inputs with a deterministic run builder (CSV first).
- Persist runs under a single authoritative RUNS_ROOT with a crash-safe registry.
- Generate the artifact set required by the Phase-1 UI and API.
- A minimal API and UI flow to create and list runs.
- Reproducible ingest and resampling rules aligned with Phase-0 specs.

## Out-of-Scope
- Live trading, broker connections, or execution controls.
- Strategy invention, strategy editing in UI, or auto-optimization.
- Multi-tenant SaaS, hosted accounts, or remote execution.
- Data marketplace, paid datasets, or secret management beyond env vars.
- Complex workflow engines or orchestration frameworks.

## Definitions

Usable:
A user can create a run from real inputs, the system generates deterministic artifacts, and the UI can list and display the run without manual file copying or hidden defaults.

Run:
A deterministic execution of the pipeline over a defined dataset, timeframe, strategy configuration, and risk configuration. A run produces an artifact set and a manifest that fully describes inputs and outputs.

Artifact Set:
The minimal set of files that the UI and API consume to display a run. At minimum this includes decision records, metrics, and a timeline, plus a manifest that enumerates all artifacts and their versions.

## Product Completion Definition

A completion-ready product core means:
- A user can create a run from CSV + selected strategy using UI and CLI.
- The created run is stored under the runs root directory and is visible in the run list.
- The workspace page renders the run strictly from artifacts.
- The system is deterministic and reproducible (same inputs -> same run id and artifacts).
- Fail-closed behavior is preserved with stable, user-explainable error codes.
- Local quality gates pass consistently.
Note: If current UI implementation is path-based, it must be treated as a temporary bridge and tracked via `docs/DECISIONS.md` (D-001).

## Security and Privacy
- No secrets are stored in the repo or run artifacts.
- Data source credentials, if any, are supplied only via environment variables or local config ignored by git.
- CSV files are treated as local inputs; paths are recorded in the manifest but never uploaded.
- Logs must avoid printing raw secrets or access tokens.

## Acceptance Journeys

Canonical user journey: docs/USER_JOURNEY.md.
1. User runs a CLI command with a CSV input and gets a new run_id with artifacts written under RUNS_ROOT.
2. User opens /runs/{run_id} and sees the chart, metrics, and timeline from the new artifacts.
3. User restarts API/UI and the run is still listed and loadable from RUNS_ROOT.
4. User provides an invalid CSV and the run creation fails closed with a stable error code.
5. User uses /runs/new to upload a CSV, creates a run, and is redirected to /runs/{run_id} with a success state.
6. User can reproduce the same run from the same inputs and obtain the same run_id and artifacts (byte-for-byte where applicable).

## Stage 1: Real Run Builder

Goal:
Deliver a deterministic run builder that creates a new run from real inputs (CSV first), writes the required artifacts, registers the run, and enables the UI to render /runs/{run_id} without manual file copying.

Inputs:
- RunCreateRequest (see CONTRACTS.md)
- CSV file path and metadata
- RUNS_ROOT

Outputs:
- RUNS_ROOT/<run_id>/ with manifest.json, decision_records.jsonl, metrics.json, timeline.json
- Registry entry in RUNS_ROOT/index.json
- /api/v1/runs includes the new run

Deliverables:
- Run builder CLI entrypoint and library function (deterministic, fail-closed).
- Manifest writer that records inputs, hashes, and artifacts.
- Registry update logic following the Storage Contract.
- Validation logic for inputs and CSV schema.

Definition of Done:
- A single CLI command creates a new run under RUNS_ROOT with required artifacts.
- run_id is deterministic for identical inputs.
- /runs/{run_id} renders with artifacts from the new run.
- Missing or invalid CSV fails with a stable error code.
- manifest.json contains schema_version, inputs_hash, and artifact list.

Mandatory Gates:
- Core verification commands: `../05_RUNBOOK_DEV_WORKFLOW.md#verification-gates`
- Stage-specific checks: `tests/phase6/test_run_builder.py`, `apps/web/scripts/ui-smoke.mjs`
Expected outcomes: core verification gates and listed stage checks pass; UI smoke reports `UI smoke OK`.

Risks and Anti-goals:
- Do not add live trading or broker integration.
- Do not invent strategy logic; only use registered strategies.
- Do not allow partial runs to appear in the registry.

## Stage 2: Durable Storage

Goal:
Make run storage crash-safe and restart-safe with a single authoritative RUNS_ROOT and an atomic registry/index.

Inputs:
- RUNS_ROOT
- Run manifest and artifacts from Stage 1

Outputs:
- Crash-safe RUNS_ROOT/index.json
- Restart persistence across API/UI restarts
- Backward-compatible read of Phase-1 fixtures

Deliverables:
- RUNS_ROOT semantics implemented across API and CLI.
- Atomic index writes with temp file replace.
- Bridging logic for Phase-1 artifacts under ARTIFACTS_ROOT.

Definition of Done:
- RUNS_ROOT is the only write target for new runs.
- Registry updates are atomic; index is valid after simulated crash.
- API/UI restart preserves run list and run metadata.
- Corrupt or partial runs never appear in listings.

Mandatory Gates:
- Core verification commands: `../05_RUNBOOK_DEV_WORKFLOW.md#verification-gates`
- Stage-specific checks: `tests/phase6/test_run_registry.py`
Expected outcomes: core verification gates and listed stage checks pass; registry checks verify atomicity and restart behavior.

Risks and Anti-goals:
- Do not create multiple competing roots.
- Do not hide invalid runs behind default fallbacks.

## Stage 3: Real Data Ingestion

Goal:
Expand ingest beyond CSV MVP with robust validation and reproducibility, while maintaining canonical 1m ingest and deterministic resampling.

Inputs:
- Data source config (CSV and provider-ready adapters)
- Ingest config (timeframe, symbol, time window)

Outputs:
- Canonical 1m dataset
- Deterministic resampled datasets
- Data quality report with gaps and validation results

Deliverables:
- CSV ingest hardened with explicit schema rules.
- Provider adapter interface (even if only CSV is implemented in this stage).
- Data quality report stored and referenced in manifest.
- Reproducibility checks for fixed windows.

Definition of Done:
- CSV ingest fails closed on invalid inputs and records errors deterministically.
- Deterministic resample follows data_timeframes.md and resampling.md.
- Data quality report is generated and referenced in manifest.
- Re-running with identical inputs yields identical outputs.

Mandatory Gates:
- Core verification commands: `../05_RUNBOOK_DEV_WORKFLOW.md#verification-gates`
- Stage-specific checks: `tests/phase6/test_ingest_csv.py`, `tests/phase6/test_data_quality.py`
Expected outcomes: core verification gates and listed stage checks pass; data quality checks verify gap and schema handling.

Risks and Anti-goals:
- Do not allow ambiguous timezones or mixed timeframes.
- Do not auto-fix or fill data unless explicitly configured and recorded.

## Stage 4: Usable UX

Goal:
Expose a safe UI flow at /runs/new to create a run using the Stage-1 builder and Stage-3 ingestion.

Inputs:
- User-provided CSV file and run parameters
- Available strategy list and risk levels

Outputs:
- Created run_id
- Redirect to /runs/{run_id}
- Visible run in the run list

Deliverables:
- /runs/new page with validation and clear error states.
- POST /api/v1/runs endpoint to trigger run creation.
- Feature flag to keep run creation off by default.

Definition of Done:
- /runs/new creates a run from CSV without manual file placement.
- UI shows progress and clear failure messages.
- Server-side validation rejects invalid inputs even if UI validates.
- New run appears in /runs and renders in /runs/{run_id}.

Mandatory Gates:
- Core verification commands: `../05_RUNBOOK_DEV_WORKFLOW.md#verification-gates`
- Stage-specific checks: `tests/phase6/test_runs_new_ui.py`, `apps/web/scripts/ui-smoke.mjs`, `apps/web/scripts/smoke.mjs`
Expected outcomes: core verification gates and listed stage checks pass; UI smoke validates run list and render.

Risks and Anti-goals:
- Do not add execution controls to UI.
- Do not block the UI indefinitely on ingest; show progress and allow retry.

## Stage 5: Reliability and Safety

Goal:
Harden run creation and ingest with health checks, limits, kill switch, and structured logs.

Inputs:
- Runtime config for limits and kill switch
- Health metrics for builder and registry

Outputs:
- Safe, observable run creation
- Structured logs and health signals
- Limits enforced at API and builder boundaries

Deliverables:
- Health endpoint includes registry and builder checks.
- Run creation rate limits and file size limits.
- Kill switch disables new run creation immediately.
- Structured logs for create, ingest, and registry update events.

Definition of Done:
- Limits are enforced and covered by tests.
- Kill switch is fail-closed and auditable.
- Health endpoint reports builder/registry readiness.
- Reliability regressions are blocked by CI gates.

Mandatory Gates:
- Core verification commands: `../05_RUNBOOK_DEV_WORKFLOW.md#verification-gates`
- Stage-specific checks: `tests/phase6/test_safety_limits.py`, `tests/phase6/test_kill_switch.py`
Expected outcomes: core verification gates and listed stage checks pass; safety checks confirm enforcement and fail-closed behavior.

Risks and Anti-goals:
- Do not add silent retries that could create duplicate runs.
- Do not allow limits to be bypassed by UI or CLI.

## UX Requirements

Minimal UI flow:
1. User visits /runs/new.
2. User uploads CSV and selects symbol, timeframe, strategy, and risk level.
3. User submits and the system creates a run.
4. UI redirects to /runs/{run_id} on success.
5. Run appears in /runs list with status and timestamps.

Error UX:
- Show a clear, user-facing error message with a stable error code.
- Do not show stack traces or internal file paths.
- Provide actionable guidance (example: missing columns, invalid timestamp format).
- Errors must not create partial runs or registry entries.

Progress and reporting:
- For long-running ingest, show a progress state (Queued, Running, Succeeded, Failed).
- The UI must not block indefinitely; show a retry option on failure.
- Run status must match API status.

## Dependencies and Milestone Demos

Dependency graph:
- Stage 1 -> Stage 2 -> Stage 3 -> Stage 4 -> Stage 5
- Stage 3 depends on Stage 1 and Stage 2 (builder + storage must exist).
- Stage 4 depends on Stage 1, Stage 2, and Stage 3 (API and ingest must be stable).
- Stage 5 depends on all prior stages.

Milestone demos:
- Stage 1: Run builder CLI creates a run from CSV; /runs/{run_id} renders the new run.
- Stage 2: Restart API/UI and the run still appears; registry remains consistent after simulated crash.
- Stage 3: CSV ingest produces canonical 1m data and a data quality report; deterministic resampling for fixed windows.
- Stage 4: /runs/new creates a run and redirects to /runs/{run_id}; UI shows progress and success state.
- Stage 5: Kill switch blocks new run creation; health endpoint reports readiness; limits enforced.




