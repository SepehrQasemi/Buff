# Contracts And Schemas

## Table Of Contents
- [Canonical Error Schema](#canonical-error-schema)
- [Alias Policy](#alias-policy)
- [Error Code Registry](#error-code-registry)
- [Artifact Contract Matrix](#artifact-contract-matrix)
- [Strategy And Plugin Contracts](#strategy-and-plugin-contracts)
- [Consolidation Notes](#consolidation-notes)

## Canonical Error Schema
All fail-closed API responses use this envelope:

```json
{
  "code": "ERROR_CODE",
  "message": "Human readable message",
  "details": {},
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message",
    "details": {}
  }
}
```

Notes:
- `code`, `message`, and `details` are required at top-level.
- Nested `error` mirrors top-level values for stable client handling.
- Runtime source: `apps/api/phase6/http.py`.

## Alias Policy
- Canonical code names in this document are the client-facing target names.
- If an alias is received from legacy endpoints, clients must map it to the canonical code before rendering user guidance.
- This PR does not change server behavior; it documents current runtime truth and compatibility mapping.

## Error Code Registry
Canonical names below are based on runtime responses in `apps/api/main.py` and current tests under `tests/phase6`, `tests/integration`, and `tests/web`.

| Canonical Code | Aliases | HTTP Status | When It Happens | Client Action (Recovery Hint) |
| --- | --- | --- | --- | --- |
| `RUNS_ROOT_UNSET` | none | `503` | `RUNS_ROOT` env is missing. Verified on `GET /api/v1/ready`, `GET /api/v1/runs`, and `POST /api/v1/runs`. | Set `RUNS_ROOT` to a repo-local directory and restart services |
| `RUNS_ROOT_MISSING` | none | `503` | `RUNS_ROOT` path does not exist | Create the directory or point env to a valid path |
| `RUNS_ROOT_INVALID` | none | `503` | `RUNS_ROOT` exists but is not a directory | Point `RUNS_ROOT` to a directory |
| `RUNS_ROOT_NOT_WRITABLE` | none | `503` | Process cannot write to `RUNS_ROOT` | Fix permissions and retry |
| `invalid_run_id` | `RUN_ID_INVALID` | `400` | Run id is malformed, traversal-like, or disallowed | Ask user to select a valid run id from list; avoid manual path fragments |
| `RUN_NOT_FOUND` | `run_not_found` | `404` | Requested run is absent in registry/filesystem | Refresh run list and choose an existing run id |
| `artifacts_root_missing` | none | `404` | Demo artifacts root is missing/unavailable | Fix `ARTIFACTS_ROOT` path for demo mode |
| `RUN_CONFIG_INVALID` | none | `400` | Invalid JSON/multipart payload, path rules, or run config fields | Fix request payload/CSV settings and retry |
| `DATA_INVALID` | none | `400` | CSV/data validation failed (timestamps, columns, numeric rules, gaps) | Correct CSV format/content and retry run creation |
| `STRATEGY_INVALID` | none | `400` | Unknown/invalid strategy configuration | Choose a validated strategy id/params |
| `RUN_EXISTS` | none | `409` | Same explicit `run_id` already exists with different inputs | Use canonical deterministic id or choose a unique run id |
| `RUN_CORRUPTED` | none | `409` | Registry points to missing/corrupt artifacts | Recreate the run to regenerate artifacts |
| `metrics_missing` | none | `404` | `metrics.json` is missing | Recreate or repair run artifacts |
| `metrics_invalid` | none | `422` | `metrics.json` cannot be parsed/validated | Recreate run artifacts |
| `decision_records_missing` | none | `404` | `decision_records.jsonl` missing | Recreate run artifacts |
| `decision_records_invalid` | none | `422` | `decision_records.jsonl` malformed | Recreate run artifacts |
| `ohlcv_missing` | none | `404` | OHLCV artifact not present for run/timeframe | Regenerate run or requested timeframe artifact |
| `ohlcv_invalid` | none | `422` | OHLCV artifact unreadable/invalid | Recreate run artifacts |
| `trades_missing` | none | `404` | Trades artifact missing | Recreate run artifacts |
| `trades_invalid` | none | `422` | Trades artifact unreadable/invalid | Recreate run artifacts |
| `timeline_missing` | none | `404` | Timeline artifact missing when artifact source required | Recreate run artifacts or use decision-derived source |
| `timeline_invalid` | none | `422` | Timeline artifact unreadable/invalid | Recreate run artifacts |
| `ARTIFACT_NOT_FOUND` | none | `404` | Requested named artifact file not found | Verify artifact name and run integrity |
| `invalid_timestamp` | none | `400` | Timestamp query parameter is malformed | Provide ISO-8601 UTC or epoch-ms timestamp |
| `invalid_time_range` | none | `400` | `start_ts` is after `end_ts` | Correct time range bounds |
| `too_many_filter_values` | none | `400` | Filter array exceeds allowed limit | Reduce number of filter values |
| `invalid_export_format` | none | `400` | Unsupported export format value | Use `csv`, `json`, or `ndjson` where supported |
| `chat_mode_invalid` | none | `400` | Unsupported chat mode requested | Select one of the advertised chat modes |
| `validation_error` | none | `422` | Request validation failed before handler logic | Correct request shape/path/query fields |
| `http_error` | none | endpoint-dependent | Wrapped framework HTTP exception fallback | Use HTTP status + code for user guidance and retry/fix flow |
| `REGISTRY_LOCK_TIMEOUT` | none | `503` | Registry lock could not be obtained | Retry after short delay |
| `REGISTRY_WRITE_FAILED` | none | `500` | Registry reconciliation/write failure | Check service logs and storage health before retry |

## Artifact Contract Matrix
This matrix is the canonical source for run artifacts.

Verified vs documented note:
- Verified by runtime checks (`verify_phase1`) and tests: endpoint behavior, error envelope, and artifact consumption paths.
- Documented expectation: canonical required/optional artifact contract for client behavior and release gates.

| Artifact | Required Core | Optional | Produced Today | Used By UI / Export |
| --- | --- | --- | --- | --- |
| `manifest.json` | yes | no | L1 | Run metadata, provenance, export report metadata |
| `decision_records.jsonl` | yes | no | L1 | Summary/timeline derivation, errors panel, export report counts |
| `metrics.json` | yes | no | L1 | Metrics tab, compare view metrics, export report required input |
| `timeline.json` | yes | no | L1 | Timeline tab, export report timeline event count |
| `trades.jsonl` | yes (L1 flow) | yes (legacy/phase variants) | L1 | Trades tab, trade markers, compare overlays, export report trade summary |
| `ohlcv_*.jsonl` | yes (chart flows) | yes (format variants) | L1 | Candlestick chart baseline, compare chart baseline |
| `equity_curve.json` | no | yes | L1 | Optional UI/stat rendering, report enrichment when present |
| `config.json` | no | yes | L1 | Audit/debug context, not required for panel rendering |
| `errors.jsonl` | no | yes | L2 safety flows | Errors panel and errors export endpoints when present |
| `report.md` | no | yes | L2 | Human-readable exported run report artifact |
| `report_summary.json` | no | yes | L2 | Optional machine-readable report summary |

Format precedence notes:
- If parquet variants are present (`trades.parquet`, `ohlcv_*.parquet`), API loaders prefer parquet; JSONL remains valid fallback.
- Optional artifacts must never silently replace required-core artifacts.

## Strategy And Plugin Contracts
- Strategy contract authority: [STRATEGY_CONTRACT.md](./STRATEGY_CONTRACT.md)
- Indicator contract authority: [INDICATOR_CONTRACT.md](./INDICATOR_CONTRACT.md)
- Governance authority: [STRATEGY_GOVERNANCE.md](./STRATEGY_GOVERNANCE.md)
- User plugin quickstart: [USER_EXTENSIBILITY.md](./USER_EXTENSIBILITY.md)

## Consolidation Notes
- Canonical contracts live in this document.
- Historical/detailed copies moved to appendix:
  - [appendix/PHASE1_API_CONTRACTS_APPENDIX.md](./appendix/PHASE1_API_CONTRACTS_APPENDIX.md)
  - [appendix/PHASE6_CONTRACTS_APPENDIX.md](./appendix/PHASE6_CONTRACTS_APPENDIX.md)
  - [appendix/ARTIFACTS_APPENDIX.md](./appendix/ARTIFACTS_APPENDIX.md)
