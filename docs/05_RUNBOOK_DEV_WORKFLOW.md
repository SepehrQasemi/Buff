# 05_RUNBOOK_DEV_WORKFLOW

Canonical operational commands for local development, verification, and recovery.
No other active document should carry runnable command blocks.

## Quickstart

```bash
python -m pip install -e ".[dev]"
npm --prefix apps/web install
```

## Verification Gates

```bash
python scripts/verify_phase1.py --with-services --real-smoke
python -m tools.release_preflight --timeout-seconds 900
python -m tools.release_gate --strict --timeout-seconds 900
```

## Contract Wiring
- canonical-error-schema: `docs/03_CONTRACTS_AND_SCHEMAS.md#canonical-error-schema`

## Service Lifecycle

```bash
python scripts/dev_start.py
python scripts/stop_services.py
```

## Online Data Plane Operations
Use online ingest via the data CLI entrypoint.

```bash
python -m src.data.cli ingest --symbols BTCUSDT ETHUSDT --since 2024-01-01T00:00:00Z --until 2024-01-03T00:00:00Z --timeframes 1m 5m 15m 1h --out data/ohlcv --report reports/data_quality.json
```

```bash
python -m src.paper.feed_generate --help
```

## Paper-Live Operations

```bash
python -m src.paper.cli_long_run --run-id paper_live_dev --duration-seconds 3600 --restart-every-seconds 300 --rotate-every-records 5000 --replay-every-records 2000
```

```bash
python -m src.audit.report_decisions --run-dir runs/paper_live_dev --out runs/paper_live_dev/summary.json
```

## Replay Operations

```bash
python -m src.audit.record_decision --input tests/fixtures/decision_payload.json --out artifacts/decisions
python -m src.audit.make_snapshot --input tests/fixtures/snapshot_payload.json --out artifacts/snapshots
python -m src.audit.replay --decision <decision_path.json> --snapshot <snapshot_path.json> --strict
```

## Reporting Operations

```bash
python scripts/export_report.py --help
```

## Troubleshooting Matrix
| Symptom | Likely Cause | Recovery |
| --- | --- | --- |
| `RUNS_ROOT_UNSET` | Missing runtime root env | Set `RUNS_ROOT` and restart services |
| Data ingest gap failure | Missing online bars or failed backfill | Re-run ingest and validate gap report |
| Replay digest mismatch | Non-deterministic or corrupted artifact path | Regenerate artifacts and rerun replay checks |
| Kill-switch active | Safety stop triggered | Inspect risk artifacts before re-arming flows |

## Pre-PR Checklist

```bash
python -m ruff format .
python -m ruff check .
python -m pytest -q
python -m tools.release_gate --strict --timeout-seconds 900
```

## References
- `docs/PROJECT_STATE.md`
- `docs/02_ARCHITECTURE_BOUNDARIES.md`
- `docs/03_CONTRACTS_AND_SCHEMAS.md`
- `docs/06_DATA_PLANE_ONLINE.md`
- `docs/07_PAPER_LIVE_FUTURES.md`
- `docs/08_RESEARCH_LOOP.md`
- `docs/09_EXECUTION_FUTURE.md`
