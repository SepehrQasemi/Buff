# First Run In 10 Minutes

This guide gets a local single-user setup running with the read-only UI, then creates
your first run via CSV upload.

## Prerequisites (3 minutes)

- Python 3.10+
- Node.js + npm

```bash
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

```bash
cd apps/web
npm install
```

## Start The Dev Servers (1 minute)

Single-command dev start (API + UI):

```bash
python scripts/dev_start.py
```

Notes:
- Defaults to `RUNS_ROOT=.runs` under the repo.
- Sets `DEMO_MODE=0`.
- The UI is read-only and artifact-driven (no execution controls).

When ready, open:

```
http://localhost:3000/runs/new
```

## Create Your First Run (3 minutes)

1. Open `/runs/new`.
2. Upload a CSV (try `tests/fixtures/phase6/sample.csv`).
3. Pick a strategy (for example, `hold`).
4. Click **Create Run**.
5. You should be redirected to `/runs/{run_id}`.

Inspect:
- Metrics tab (check `num_trades`).
- Trades tab.
- Timeline tab.

## Optional: Real-Smoke Check (3 minutes)

Stop the dev servers, then run:

```bash
python scripts/verify_phase1.py --with-services --real-smoke
```

This spins up API/UI and validates the end-to-end flow (file upload + UI load).

## Troubleshooting

**RUNS_ROOT_UNSET**
- Cause: `RUNS_ROOT` is missing.
- Fix: use `python scripts/dev_start.py` or set `RUNS_ROOT` to a repo-local path (e.g. `.runs`).

**Port already in use**
- Cause: 8000/3000 are occupied.
- Fix: stop the process or set `API_PORT` / `UI_PORT` env vars, e.g.:
  - PowerShell: `$env:API_PORT=8001; $env:UI_PORT=3001; python scripts/dev_start.py`
  - Bash: `API_PORT=8001 UI_PORT=3001 python scripts/dev_start.py`

**DATA_INVALID**
- Cause: CSV missing required fields or invalid timestamps.
- Fix: ensure `open, high, low, close, volume` columns and a timestamp column.

**RUN_CORRUPTED**
- Cause: missing artifact files in a run directory.
- Fix: delete the run folder under `RUNS_ROOT` and create the run again.

**Missing artifacts / metrics_missing**
- Cause: partial or failed run.
- Fix: rerun with a valid CSV; ensure `RUNS_ROOT` is writable and local to the repo.
