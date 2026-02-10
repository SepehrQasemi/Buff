# VERIFY_PHASE1_DIAGNOSIS — Phase-1 Reproducibility
Date: 2026-02-10

**Summary**
- `scripts/verify_phase1.py --with-services` completes successfully within ~2 minutes when allowed >300s.
- Prior timeout was caused by an insufficient external timeout (120s), not a true stall.
- Phase-1 is reproducible on this machine with current dependencies; runtime is dominated by `pytest`.

**Execution Timeline (Timestamped)**
- 2026-02-10T11:09:26.678+01:00 Start Phase-1 services.
- 2026-02-10T11:09:29.034+01:00 API ready (uvicorn on 127.0.0.1:8000).
- 2026-02-10T11:09:41.703+01:00 UI dev server start (Next.js `next dev --port 3000`).
- 2026-02-10T11:09:47.130+01:00 UI ready.
- 2026-02-10T11:09:47.603+01:00 Step `ruff check` start.
- 2026-02-10T11:09:47.755+01:00 Step `ruff check` OK.
- 2026-02-10T11:09:47.773+01:00 Step `ruff format` start.
- 2026-02-10T11:09:47.860+01:00 Step `ruff format` OK.
- 2026-02-10T11:09:47.860+01:00 Step `pytest` start.
- 2026-02-10T11:11:29.026+01:00 Step `pytest` OK.
- 2026-02-10T11:11:30.381+01:00 Step `ui smoke` start.
- 2026-02-10T11:11:31.528+01:00 Step `ui smoke` OK.
- 2026-02-10T11:11:31.528+01:00 Phase-1 verification complete.
- 2026-02-10T11:11:31.529+01:00 Teardown: stopping UI and API.

**Exact Blocking Point**
- No blocking/stall observed in this run.
- Prior timeout was triggered by the external runner timeout (120s) during the `pytest` step. The full run time exceeds 120s.

**Services and Dependencies Involved**
- API: `uvicorn apps.api.main:app` started by `scripts/verify_phase1.py`.
- UI: `npm run dev -- --port <port>` (Next.js dev server).
- Tooling: `ruff`, `pytest`, `node`, `npm`.
- No Docker is used by `verify_phase1.py` (Docker compose exists at `docker-compose.yml` but is not invoked).

**Script/Bootstrap Inspection**
- `scripts/verify_phase1.py`
  - Starts API and UI via subprocess with `--with-services`.
  - Waits for API `/api/v1/health` and UI `/runs/phase1_demo` marker `data-testid="chart-workspace"`.
  - Runs steps in order: `ruff check`, `ruff format --check`, `pytest -q`, `node apps/web/scripts/ui-smoke.mjs`.
  - Uses `ARTIFACTS_ROOT=tests/fixtures/artifacts` for API service.
- `docker-compose.yml`
  - Defines `api` and `web` services for containerized use but is unused by `verify_phase1.py`.
- UI smoke script: `apps/web/scripts/ui-smoke.mjs`
  - Requires `/api/v1/runs` and `/runs/{id}` to work; verifies trade markers if present.

**Expected vs Actual Artifact Outputs**
- Expected artifacts for Phase-1 fixture: `tests/fixtures/artifacts/phase1_demo/`.
- Present artifacts:
  - `decision_records.jsonl`
  - `trades.parquet`
  - `metrics.json`
  - `ohlcv_1m.parquet`
  - `timeline.json`
- UI smoke succeeded with `run_id=phase1_demo`, confirming artifacts were readable by API/UI.

**Determinism vs Intermittence**
- Deterministic runtime observed: ~125s total.
- The timeout seen previously is consistent with a fixed 120s external timeout and a `pytest` duration of ~100s+. This is deterministic, not intermittent.
- Potential intermittent risks (not observed): slow Next.js dev startup on cold cache, port contention (handled by port-fallback logic), or slow disk/AV scans.

**Root-Cause Hypotheses (Ranked)**
1. Timeout threshold too low for full Phase-1 run. `pytest -q` alone can take ~100s; total run ~125s. This explains the prior timeout.
2. Cold Next.js dev startup can occasionally exceed the script’s internal `wait_for_http` timeout (120s) on slower machines or after cache invalidation.
3. External runner or shell pipeline behavior can report non-zero exit code even when the script completes (observed once with timestamped pipeline). This should be verified without a pipeline if it recurs.

**Recommendation**
- (b) Relax timeout to >=300s in CI or any external runner that invokes `verify_phase1.py --with-services`.
- (d) Split `verify_phase1.py` into sub-verifiers (services startup, lint, tests, UI smoke) so each can be run and timed independently if needed.
- (c) Optionally mark UI smoke as optional in constrained environments where Next dev startup is slow.

**Notes**
- This diagnosis run used timestamped logging via PowerShell pipeline; `verify_phase1.py` itself does not expose a logging flag.
- If you want absolute exit-code confirmation, re-run `python scripts/verify_phase1.py --with-services` without piping and check `$LASTEXITCODE`.

**Exit Code Verification (No Pipeline)**
- Command (PowerShell): `python scripts/verify_phase1.py --with-services; $LASTEXITCODE`
- Observed exit code: `0`
- Conclusion: `verify_phase1.py --with-services` exits cleanly when run without piping; prior non-zero exit codes were pipeline-related.

**Supported Invocation (Recommended)**
- `python scripts/verify_phase1.py --with-services`
- If exit code must be captured explicitly in PowerShell: `python scripts/verify_phase1.py --with-services; $LASTEXITCODE`
