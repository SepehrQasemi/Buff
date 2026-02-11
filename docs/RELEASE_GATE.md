# Release Gate Procedure

This document defines a repeatable, non-flaky release gate run for Windows/PowerShell.
Use this when validating Phase-1 UI + API readiness and when producing proof artifacts.

## When To Use `verify_phase1 --with-services --no-teardown`
- Use it when you need to start API/UI locally and keep them running for follow-up checks.
- The script starts API/UI, runs ruff/pytest/ui-smoke, and leaves services up when `--no-teardown` is set.
- The standalone `ui-smoke` must run while services are up.

## Why `ui-smoke` Must Run While Services Are Running
`ui-smoke` queries the API and fetches HTML from the running UI:
- API: `http://127.0.0.1:8000/api/v1`
- UI: `http://127.0.0.1:3000` (or `3001` if `3000` is busy)

If UI/API are not running, `ui-smoke` will fail with a fetch error.

## Port Cleanup + Next Dev Lock Rules
- Ports used: `3000`, `3001`, `8000`.
- If ports are occupied, terminate the owning processes before starting services.
- Only remove `apps/web/.next/dev/lock` if **no** Next.js dev process is running.
- Never delete any other `.next` content or repo data.

## Expected Success Signals
You should see:
- `verify_phase1` output with `OK ruff check`, `OK pytest`, and `OK ui smoke`.
- Standalone `ui-smoke` output: `UI smoke OK { runId: 'phase1_demo' }`.
- `ruff check` passes.
- `pytest -q` passes.
- A proof report written to `reports/release_gate_proof_YYYYMMDD-HHMM.md`.

## Recommended Command (PowerShell)
```
powershell -ExecutionPolicy Bypass -File scripts/release_gate.ps1
```

The script handles:
- Port cleanup and lock cleanup
- `verify_phase1 --with-services --no-teardown`
- Standalone `ui-smoke`
- `ruff check` + `pytest -q` with timeout retry
- Service teardown by port
- Proof report output
