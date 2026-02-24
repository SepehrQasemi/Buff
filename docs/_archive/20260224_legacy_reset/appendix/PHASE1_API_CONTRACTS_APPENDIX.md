ARCHIVED — NOT AUTHORITATIVE
Superseded by new documentation reset 2026-02-24.
Do not rely on this file for current stage or product direction.

# Appendix: Phase-1 API Contracts (Historical Detailed Notes)

Historical source retained from `docs/PHASE1_API_CONTRACTS.md` before PR2 contract unification.
Canonical contracts now live in [../03_CONTRACTS_AND_SCHEMAS.md](../03_CONTRACTS_AND_SCHEMAS.md).

---

# Phase-1 Artifacts API Contracts (UI Core)

These contracts describe the read-only JSON endpoints consumed by the Phase-1 chart workspace UI.
All endpoints are deterministic, read-only, and fail-closed: missing or invalid artifacts return
an actionable HTTP error (typically 404 for missing artifacts, 400 for invalid params).

## Metadata
- contractVersion: 1

## Phase-1 Invariants (Hard Lock)
- UI is read-only (no execution, no broker controls, no live trading).
- Artifacts are the sole source of truth (no recomputation in UI or API).
- Fail-closed on missing or corrupted data (never return silent defaults).
- Breaking changes require a contractVersion bump.

## UI Contract (Phase-1)
- The chart workspace root (`/runs/{run_id}`) must include
  `data-testid="chart-workspace"` as a stable DOM marker.
- This marker is relied upon by the Phase-1 verification gate and must not be removed
  without a contractVersion bump.

## Base
- Preferred prefix: `/api/v1`
- Legacy prefix: `/api` (same handlers)

## Endpoints

### 1) List Runs
`GET /runs`

Response (array of runs):
- `id`: run id (string)
- `created_at`: UTC ISO timestamp (string)
- `status`: `OK` | `INVALID`
- `strategy`: strategy id/name if known (string | null)
- `symbols`: symbols discovered from decision records (string[] | null)
- `timeframe`: timeframe discovered from decision records (string | null)
- `has_trades`: whether `trades.parquet` exists (bool)
- `artifacts`: object of artifact presence booleans
  - `decisions`, `trades`, `metrics`, `ohlcv`, `timeline`, `risk_report`, `manifest`

### 2) Run Summary
`GET /runs/{run_id}/summary`

Response (object):
- Existing decision summary fields:
  - `min_timestamp`, `max_timestamp`, `counts_by_action`, `counts_by_severity`,
    `malformed_lines_count`, `malformed_samples`, `malformed_samples_detail`
- `run_id`
- `artifacts`: same shape as list runs
- `provenance`:
  - `strategy_id`, `strategy_version`, `data_snapshot_hash`, `feature_snapshot_hash`
- `risk`:
  - `level` (1..5 or null)
  - `state` (GREEN/YELLOW/RED or null)
  - `permission` (ALLOW/RESTRICT/BLOCK or null)
  - `blocked` (bool)
  - `reason` (string | null)
  - `rule_id` (string | null)
  - `policy_type` (`hard_cap` | `user_policy` | `unknown` | null)

### 3) OHLCV Candles
`GET /runs/{run_id}/ohlcv?symbol=BTCUSDT&timeframe=1m&start_ts=...&end_ts=...&limit=...`

Response:
- `run_id`, `symbol`, `timeframe`
- `count`, `start_ts`, `end_ts`
- `candles`: array of `{ ts, open, high, low, close, volume }`

Notes:
- Supports `start_ts`/`end_ts` (UTC ISO) and `limit` (caps rows, max 10000).
- Fails closed if the OHLCV artifact is missing or invalid.

### 4) Trades
`GET /runs/{run_id}/trades?start_ts=...&end_ts=...&page=1&page_size=200`

Response:
- Existing pagination shape: `total`, `page`, `page_size`, `results`, `timestamp_field`

### 5) Trade Markers
`GET /runs/{run_id}/trades/markers?start_ts=...&end_ts=...`

Response:
- `run_id`, `total`
- `markers`: array of `{ timestamp, price, side, marker_type, pnl, trade_id }`

### 6) Metrics Summary
`GET /runs/{run_id}/metrics`

Response:
- Raw JSON from `metrics.json` with `run_id` injected.

### 7) Timeline Events
`GET /runs/{run_id}/timeline?source=auto|decisions|artifact`

Response:
- `run_id`, `total`
- `events`: array of `{ timestamp, type, title, detail, severity, risk }`

Notes:
- `source=auto` uses `timeline.json` / `timeline_events.json` / `risk_timeline.json`
  if present; otherwise derives timeline from decision records.
- `source=decisions` forces derivation from decision records.

## Fail-Closed Behavior
- Missing required artifacts return HTTP 404 with a structured error payload.
- Invalid timestamps or parameters return HTTP 400.
- Invalid/unsupported artifact formats return HTTP 422.

### Error Schema

Errors are returned as a stable JSON object:

```json
{ "code": "error_code", "message": "Human readable message", "details": {} }
```

### Allowed Error Codes

| Code | Description |
| --- | --- |
| `artifacts_root_missing` | Artifacts root path is missing/unavailable. |
| `invalid_run_id` | Run id failed validation (traversal or invalid format). |
| `run_not_found` | Run directory does not exist under artifacts root. |
| `decision_records_missing` | `decision_records.jsonl` is missing. |
| `decision_records_invalid` | `decision_records.jsonl` contains invalid JSON lines. |
| `trades_missing` | `trades.parquet` is missing. |
| `trades_invalid` | `trades.parquet` is invalid or unreadable. |
| `ohlcv_missing` | OHLCV artifact is missing for the requested run/timeframe. |
| `ohlcv_invalid` | OHLCV artifact is invalid or unreadable. |
| `metrics_missing` | `metrics.json` is missing. |
| `metrics_invalid` | `metrics.json` is invalid or unreadable. |
| `timeline_missing` | Timeline artifact is missing. |
| `timeline_invalid` | Timeline artifact is invalid or unreadable. |
| `invalid_timestamp` | Timestamp parameter is invalid/unsupported. |
| `invalid_time_range` | `start_ts` is after `end_ts`. |
| `too_many_filter_values` | Filter value count exceeds limit. |
| `invalid_export_format` | Export format is unsupported. |
| `chat_mode_invalid` | Chat mode is unsupported or invalid. |
| `validation_error` | Request validation failed (query/path validation). |
| `http_error` | Unhandled HTTP errors (fallback wrapper). |

### Timestamp Normalization

- Naive timestamps (no timezone suffix) are treated as UTC.
- All API responses return timestamps normalized to UTC with a trailing `Z`.
