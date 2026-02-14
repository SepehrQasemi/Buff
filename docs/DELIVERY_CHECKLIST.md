---
# Delivery Checklist (Operational)

This checklist defines the proof required to claim the product core is complete and stable.

## Preconditions
- You are on the main branch and synced.
- Local environment has Python and Node installed.
- You can start API and UI locally.

## Proof Set A — Clean repo and reproducible environment
1) `git status -sb` shows a clean tree.
2) `python --version` and `node --version` are recorded.
3) Dependencies can be installed using the documented commands.

## Proof Set B — Quality gates (must pass)
Run these and record exit codes:
1) Verification with services
2) Phase 6 release gate (repo root):
   - `python src/tools/phase6_release_gate.py`
   - or `python -m src.tools.phase6_release_gate`
3) Strict release gate
4) Runs gate for deterministic creation/listing
5) UI smoke

Expected outcome:
- All commands exit with code 0.

## Proof Set C — Create a run and observe it end-to-end
### C1) Create via UI
1) Start API (example PowerShell):
   `"$env:RUNS_ROOT='C:\\dev\\Buff\\.runs'; $env:DEMO_MODE='0'; python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000"`
2) Start UI:
   `cd apps/web && npm install && npm run dev -- --port 3000`
3) Open `http://localhost:3000/runs/new`.
4) Provide CSV input (currently repo-relative path-based; file upload is the target).
5) Choose a strategy and parameters.
6) Create the run.

Proof:
- A run id is returned.
- The run appears in the run list endpoint: `GET http://127.0.0.1:8000/api/v1/runs` returns `200` and contains the run id.
- The workspace page opens successfully.
- The run directory exists under RUNS_ROOT with artifacts (example): `Get-ChildItem $env:RUNS_ROOT\\<run_id>`.

### C2) Create via CLI
1) Use CLI to create a run from the same inputs as the UI run (PowerShell example):
   `Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/runs -ContentType application/json -Body '{\"schema_version\":\"1.0.0\",\"data_source\":{\"type\":\"csv\",\"path\":\"tests/fixtures/phase6/sample.csv\",\"symbol\":\"BTCUSDT\",\"timeframe\":\"1m\"},\"strategy\":{\"id\":\"hold\",\"params\":{}},\"risk\":{\"level\":3},\"costs\":{\"commission_bps\":0,\"slippage_bps\":0}}'`

Proof:
- The run id matches the UI run for identical canonical inputs (determinism).
- Re-running is idempotent (same run id, no duplication).

### C3) Verify run endpoints
1) `GET http://127.0.0.1:8000/api/v1/runs/<run_id>/summary` returns `200` and includes `run_id` and `artifacts`.
2) `GET http://127.0.0.1:8000/api/v1/runs/<run_id>/trades` returns `200` and includes `results`.
3) `GET http://127.0.0.1:8000/api/v1/runs/<run_id>/ohlcv?timeframe=1m` returns `200` and includes `candles`.
4) `GET http://127.0.0.1:8000/api/v1/runs/<run_id>/metrics` returns `200` and includes `total_return`, `max_drawdown`, `num_trades`, `win_rate`.
5) `GET http://127.0.0.1:8000/api/v1/runs/<run_id>/timeline?source=artifact` returns `200` and includes `events`.

## Proof Set D — Storage and registry invariants
Proof requirements:
- User-created runs live under the runs root directory.
- Registry index updates are atomic (no partial entries).
- Partial runs do not appear in the run list.

Proof commands:
1) `Get-Content $env:RUNS_ROOT\\index.json` includes the run id and status not `CORRUPTED`.
2) `Get-ChildItem $env:RUNS_ROOT\\<run_id>` shows `manifest.json`, `metrics.json`, `timeline.json`, `trades.jsonl`, `ohlcv_1m.jsonl`, `decision_records.jsonl`.

## Proof Set E — Failure modes are user-explainable
Verify the UI and API surface clear messages for:
- Runs root missing/misconfigured
- CSV invalid/unreadable
- Strategy/indicator validation failure
- Run already exists (idempotent)
- API unreachable

Proof commands:
1) Unset RUNS_ROOT and restart API:
   `Remove-Item Env:RUNS_ROOT; $env:DEMO_MODE='0'; python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000`
   `GET http://127.0.0.1:8000/api/v1/runs` returns `503` with `RUNS_ROOT_UNSET`.
   UI shows a message with a short title and a `Fix:` step.
2) Invalid CSV:
   `POST /api/v1/runs` with a bad CSV path returns `DATA_SOURCE_NOT_FOUND` or `DATA_INVALID`.
   UI shows a message with a short title and a `Fix:` step.
3) Demo mode:
   `Remove-Item Env:RUNS_ROOT; $env:DEMO_MODE='1'; $env:ARTIFACTS_ROOT='C:\\path\\to\\demo\\artifacts'; python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000`
   Open `http://localhost:3000/runs` and confirm the demo banner + DEMO badges.

## Documentation links
- Product Roadmap: `docs/PRODUCT_ROADMAP.md`
- Decisions: `docs/DECISIONS.md`
- User Journey: `docs/USER_JOURNEY.md`
- Architecture Boundaries: `docs/ARCHITECTURE_BOUNDARIES.md`
---

