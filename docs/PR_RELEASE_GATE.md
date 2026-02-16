# Release Gate: local preflight + CI workflow (fail-closed, timed, reported)

## Summary

- Adds `tools.release_preflight` to safely sync `main` (ff-only) and run the release gate.
- Adds `tools.release_gate` with strict/non-strict modes, per-step timeouts, and JSON reports.
- Allows preflight to pass when local `main` is ahead of `origin/main` (ancestor check).
- Adds CI workflow to run the strict gate and upload the report artifact.

## Canonical Command Source

Use the runbook for all executable commands:
- [05_RUNBOOK_DEV_WORKFLOW.md#verification-gates](./05_RUNBOOK_DEV_WORKFLOW.md#verification-gates)
- [05_RUNBOOK_DEV_WORKFLOW.md#pre-pr-checklist](./05_RUNBOOK_DEV_WORKFLOW.md#pre-pr-checklist)

## CI

Workflow: `release-gate.yml`

- Installs dependencies using `uv sync --frozen --extra dev`
- Runs the strict release gate workflow step defined in CI config.
- Uploads `reports/release_gate_report.json` as an artifact

## Safety Properties

- Fail-closed on any failing step
- Uses `git pull --ff-only origin main` during preflight
- Verifies `origin/main` is an ancestor of `HEAD` (ahead allowed, diverged fails)
- No push-to-main requirement
- Per-step timeouts prevent hangs
- Detailed JSON reporting for auditability

## Proof (local)

- `release_gate: PASS`
- See `reports/release_gate_report.json`
- See `reports/release_preflight_report.json`
