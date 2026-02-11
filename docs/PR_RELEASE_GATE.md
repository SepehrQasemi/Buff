PR Title:
Release Gate: local preflight + CI workflow (fail-closed, timed, reported)

PR Description:

## Summary
- Add local `tools.release_preflight` to sync main safely (ff-only) and run the gate.
- Add local `tools.release_gate` with strict/non-strict modes, per-step timeouts, and JSON reports.
- Allow preflight to pass when local `main` is ahead of `origin/main` (ancestor check).
- Add/align CI workflow to run the release gate and upload the report artifact.

## Local Usage
```bash
python -m tools.release_preflight --timeout-seconds 900
python -m tools.release_gate --strict --timeout-seconds 900
```

## CI
- Workflow: `.github/workflows/release-gate.yml`
- Installs dependencies with `uv sync --frozen --extra dev` and runs the strict gate.
- Uploads `reports/release_gate_report.json` as an artifact.

## Safety Properties
- Fail-closed on any failing step.
- Uses `git pull --ff-only origin main` during preflight.
- Verifies `origin/main` is an ancestor of `HEAD` (ahead is allowed; diverged fails).
- No push-to-main requirement.

## Proof
- Local gate PASS (see `reports/release_gate_report.json`).
- Local preflight PASS (see `reports/release_preflight_report.json`).
