# Contracts And Schemas

## Table Of Contents
- [Canonical Error Schema](#canonical-error-schema)
- [Alias Policy](#alias-policy)
- [Error Code Registry](#error-code-registry)
- [Artifact Contract Matrix](#artifact-contract-matrix)
- [S3 Fixed-Point Numeric Policy](#s3-fixed-point-numeric-policy)
- [SimulationRunRequest Schema](#simulationrunrequest-schema)
- [SimulationRunResult Schema](#simulationrunresult-schema)
- [S3 Canonicalization And Digest Rules](#s3-canonicalization-and-digest-rules)
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

## S3 Fixed-Point Numeric Policy
- Money, price, quantity, fee, and PnL fields in S3 contracts MUST use fixed-point integers with `e8` scale (`*_e8`).
- Floating-point JSON numbers are forbidden in `SimulationRunRequest`, `SimulationRunResult`, and canonicalized S3 artifacts.
- Contract validators for S3 schemas MUST reject payloads that encode money/price/qty as float or decimal string.

## SimulationRunRequest Schema
Schema version: `s3.simulation_run_request.v1`  
Normative stage spec: [stages/S3_CONTROLLED_EXECUTION_SIMULATION_SPEC.md](./stages/S3_CONTROLLED_EXECUTION_SIMULATION_SPEC.md)

Top-level field contract:

| Field | Type | Required | Constraints |
| --- | --- | --- | --- |
| `schema_version` | string | yes | Must equal `s3.simulation_run_request.v1`. |
| `tenant_id` | string | yes | Regex: `^[a-z0-9][a-z0-9_-]{2,63}$`. Must match authenticated tenant context. |
| `artifact_ref` | string | yes | Relative canonical reference. Must not contain `..`, backslash, or absolute path prefix. |
| `artifact_sha256` | string | yes | Regex: `^[a-f0-9]{64}$`. Lowercase hex SHA-256 of artifact bytes. |
| `dataset_ref` | string | yes | Relative canonical reference. Must not contain `..`, backslash, or absolute path prefix. |
| `dataset_sha256` | string | yes | Regex: `^[a-f0-9]{64}$`. Lowercase hex SHA-256 of dataset bytes. |
| `config` | object | yes | Deterministic runtime policy object. |
| `config_sha256` | string | yes | Regex: `^[a-f0-9]{64}$`. SHA-256 of canonicalized `config` bytes. |
| `seed` | integer | yes | Range: `0..9223372036854775807`. |
| `engine` | object | yes | Engine identity and pinned version. |

`config` field contract:

| Field | Type | Required | Constraints |
| --- | --- | --- | --- |
| `clock_source` | string | yes | Must equal `dataset_event_time`. |
| `timestamp_format` | string | yes | Must equal `epoch_ms`. |
| `event_order_key` | string | yes | Must equal `event_seq`. |
| `numeric_encoding` | string | yes | Must equal `fixed_e8_int`. |
| `rounding_mode` | string | yes | Must equal `half_even`. |
| `price_scale` | integer | yes | Must equal `8`. |
| `qty_scale` | integer | yes | Must equal `8`. |
| `cash_scale` | integer | yes | Must equal `8`. |

`engine` field contract:

| Field | Type | Required | Constraints |
| --- | --- | --- | --- |
| `name` | string | yes | Regex: `^[a-z0-9][a-z0-9._-]{1,63}$`. |
| `version` | string | yes | SemVer regex: `^(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)(?:-[0-9A-Za-z.-]+)?(?:\\+[0-9A-Za-z.-]+)?$`. `latest` is forbidden. |
| `build_sha` | string | no | Regex: `^[a-f0-9]{7,64}$`. |

Complete example payload:

```json
{
  "artifact_ref": "runs/run_20260218_0001/manifest.json",
  "artifact_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "config": {
    "cash_scale": 8,
    "clock_source": "dataset_event_time",
    "event_order_key": "event_seq",
    "numeric_encoding": "fixed_e8_int",
    "price_scale": 8,
    "qty_scale": 8,
    "rounding_mode": "half_even",
    "timestamp_format": "epoch_ms"
  },
  "config_sha256": "abababababababababababababababababababababababababababababababab",
  "dataset_ref": "datasets/btcusdt_1m_2025_q4.parquet",
  "dataset_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "engine": {
    "build_sha": "93a0cd895db7f100fa7ae01a6d71470f1f30cd50",
    "name": "buff-sim",
    "version": "1.0.0"
  },
  "schema_version": "s3.simulation_run_request.v1",
  "seed": 42,
  "tenant_id": "alice"
}
```

## SimulationRunResult Schema
Schema version: `s3.simulation_run_result.v1`

Top-level field contract:

| Field | Type | Required | Constraints |
| --- | --- | --- | --- |
| `schema_version` | string | yes | Must equal `s3.simulation_run_result.v1`. |
| `tenant_id` | string | yes | Must equal request `tenant_id`. |
| `simulation_run_id` | string | yes | Regex: `^sim_[a-f0-9]{16,64}$`. Derived from `request_digest_sha256`. |
| `request_digest_sha256` | string | yes | Regex: `^[a-f0-9]{64}$`. |
| `status` | string | yes | Enum: `succeeded`, `failed`. |
| `engine` | object | yes | Same contract as request `engine`. |
| `fills` | object | yes | Fills artifact metadata and entries structure. |
| `metrics` | object | yes | Metrics artifact metadata and namespaced values map. |
| `traces` | object | yes | Event log artifact metadata. |
| `report_refs` | array<object> | yes | At least one report object; each object includes digest. |
| `digests` | object | yes | Required digest keys are listed below. |

`fills` object contract:

| Field | Type | Required | Constraints |
| --- | --- | --- | --- |
| `artifact_ref` | string | yes | Relative canonical path for fills JSONL artifact. |
| `sha256` | string | yes | Regex: `^[a-f0-9]{64}$`. |
| `row_count` | integer | yes | `>= 0`. Must equal `entries.length` when entries are embedded. |
| `entries` | array<object> | yes | Ordered by `event_seq` ascending. |

Fill entry contract (`fills.entries[]` and `fills.jsonl` row schema):

| Field | Type | Required | Constraints |
| --- | --- | --- | --- |
| `event_seq` | integer | yes | Starts at `1`; strictly increasing by `+1` with no gaps. |
| `ts_epoch_ms` | integer | yes | Unix epoch milliseconds (`>= 0`). |
| `order_id` | string | yes | Regex: `^[A-Za-z0-9._:-]{1,128}$`. |
| `symbol` | string | yes | Regex: `^[A-Z0-9._-]{1,32}$`. |
| `side` | string | yes | Enum: `BUY`, `SELL`. |
| `price_e8` | integer | yes | Fixed-point price in `1e-8` units; `> 0`. |
| `qty_e8` | integer | yes | Fixed-point quantity in `1e-8` units; `> 0`. |
| `fee_e8` | integer | yes | Fixed-point fee in `1e-8` units; `>= 0`. |

`metrics` object contract:

| Field | Type | Required | Constraints |
| --- | --- | --- | --- |
| `artifact_ref` | string | yes | Relative canonical path for metrics JSON artifact. |
| `sha256` | string | yes | Regex: `^[a-f0-9]{64}$`. |
| `values` | object | yes | Map of namespaced metric keys to JSON integer values only. |

Metric key/value rules:
- Keys MUST match `^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*(?:_e8|_i64)$`.
- Values MUST be JSON integers.
- Keys ending `_e8` are fixed-point values scaled by `1e8`.
- Keys ending `_i64` are unscaled integer counters.
- Decimal strings and floating-point JSON numbers are forbidden in `metrics.values`.

`digests` object required keys:

| Key | Meaning |
| --- | --- |
| `request_sha256` | Canonical `SimulationRunRequest` bytes digest. |
| `result_sha256` | Canonical `SimulationRunResult` bytes digest. |
| `manifest_sha256` | Canonical manifest artifact digest for this simulation run. |
| `event_log_sha256` | Canonical event log JSONL digest; must equal `traces.sha256`. |
| `fills_sha256` | Canonical fills JSONL digest; must equal `fills.sha256`. |
| `metrics_sha256` | Canonical metrics JSON digest; must equal `metrics.sha256`. |
| `report_sha256` | Canonical digest of the primary report referenced by `report_refs[0]`. |

Complete example payload:

```json
{
  "digests": {
    "event_log_sha256": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
    "fills_sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    "manifest_sha256": "3333333333333333333333333333333333333333333333333333333333333333",
    "metrics_sha256": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
    "report_sha256": "1111111111111111111111111111111111111111111111111111111111111111",
    "request_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    "result_sha256": "2222222222222222222222222222222222222222222222222222222222222222"
  },
  "engine": {
    "build_sha": "93a0cd895db7f100fa7ae01a6d71470f1f30cd50",
    "name": "buff-sim",
    "version": "1.0.0"
  },
  "fills": {
    "artifact_ref": "fills.jsonl",
    "entries": [
      {
        "event_seq": 1,
        "fee_e8": 1250,
        "order_id": "ord_000001",
        "price_e8": 10125000000,
        "qty_e8": 150000000,
        "side": "BUY",
        "symbol": "BTCUSDT",
        "ts_epoch_ms": 1735689600000
      }
    ],
    "row_count": 1,
    "sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
  },
  "metrics": {
    "artifact_ref": "metrics.json",
    "sha256": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
    "values": {
      "perf.net_pnl_e8": 123456789,
      "risk.max_drawdown_e8": 10420000,
      "trade.fill_count_i64": 1
    }
  },
  "report_refs": [
    {
      "artifact_ref": "report_summary.json",
      "kind": "summary",
      "sha256": "1111111111111111111111111111111111111111111111111111111111111111"
    }
  ],
  "request_digest_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "schema_version": "s3.simulation_run_result.v1",
  "simulation_run_id": "sim_6dfd4f6b63be4f84",
  "status": "succeeded",
  "tenant_id": "alice",
  "traces": {
    "artifact_ref": "traces.jsonl",
    "event_count": 8921,
    "sha256": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
  }
}
```

## S3 Canonicalization And Digest Rules
The following rules are mandatory for `SimulationRunRequest`, `SimulationRunResult`, and S3 artifacts:

1. Encoding: UTF-8 only.
2. Encoding BOM policy: UTF-8 BOM is forbidden.
3. Newlines: line ending MUST be `\n` (LF); `\r\n` is forbidden in canonical bytes.
4. JSON key ordering: recursively sort object keys lexicographically by UTF-8 codepoint.
5. JSON spacing: compact serialization only with separators `,` and `:` and no surrounding spaces.
6. JSON document framing: no trailing spaces and no trailing newline for single JSON files.
7. Numeric policy:
   - Monetary and quantity fields MUST use fixed-point integers (`*_e8`) only.
   - JSON floating-point numbers are forbidden in request/result canonical fields.
   - `metrics.values` values MUST be JSON integers only (`*_e8` scaled by `1e8`, `*_i64` unscaled).
   - `NaN`, `Infinity`, and `-Infinity` are forbidden everywhere.
8. Timestamp policy: epoch milliseconds as integer fields (`*_epoch_ms`) only.
9. JSONL ordering:
   - `fills.jsonl` and `traces.jsonl` rows MUST be ordered by `event_seq` ascending.
   - First `event_seq` MUST be `1`.
   - Sequence MUST increase by exactly `+1` with no gaps.

Digest procedure:
- `request_sha256`: SHA-256 over canonical request JSON bytes.
- `result_sha256`: SHA-256 over canonical result JSON bytes.
- `fills_sha256`: SHA-256 over canonical `fills.jsonl` bytes (`\n`-delimited canonical JSON lines).
- `event_log_sha256`: SHA-256 over canonical `traces.jsonl` bytes.
- `metrics_sha256`: SHA-256 over canonical `metrics.json` bytes.
- `manifest_sha256`: SHA-256 over canonical simulation manifest JSON bytes.
- `report_sha256`: SHA-256 over canonical bytes of the primary report file in `report_refs[0]`.

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
