# 03_CONTRACTS_AND_SCHEMAS

## Scope
This document defines active contract expectations for Buff's refoundation stage.
It does not define current stage authority.

## Canonical Error Envelope
Fail-closed responses must use this envelope shape:

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

Rules:
- `code`, `message`, and `details` are required.
- Nested `error` mirrors top-level values.
- Unknown codes are treated as fatal by default clients.

## Canonical Error Schema
Reference anchor: `canonical-error-schema`.
Canonical error envelope and error-code registry are defined in this document.

## Error Code Registry
The following API error codes are currently documented:

- `artifacts_root_missing`
- `chat_mode_invalid`
- `decision_records_invalid`
- `decision_records_missing`
- `http_error`
- `invalid_export_format`
- `invalid_time_range`
- `invalid_timestamp`
- `metrics_invalid`
- `metrics_missing`
- `ohlcv_invalid`
- `ohlcv_missing`
- `run_not_found`
- `timeline_invalid`
- `timeline_missing`
- `too_many_filter_values`
- `trades_invalid`
- `trades_missing`
- `validation_error`

## S2 Runtime Error Registry
The S2 runtime and artifact validation layer uses this allowed error-code set:

- `ARTIFACT_MISSING`
- `DATA_INTEGRITY_FAILURE`
- `DIGEST_MISMATCH`
- `INPUT_DIGEST_MISMATCH`
- `INPUT_INVALID`
- `INPUT_MISSING`
- `MISSING_CRITICAL_FUNDING_WINDOW`
- `ORDERING_INVALID`
- `SCHEMA_INVALID`
- `SIMULATION_FAILED`

S2 precedence contract (`resolve_error_code`) is deterministic:
1. `SCHEMA_INVALID`
2. `ARTIFACT_MISSING`
3. `DIGEST_MISMATCH`
4. `INPUT_DIGEST_MISMATCH`
5. `INPUT_MISSING`
6. `INPUT_INVALID`
7. `MISSING_CRITICAL_FUNDING_WINDOW`
8. `DATA_INTEGRITY_FAILURE`
9. `ORDERING_INVALID`
10. `SIMULATION_FAILED`

## Active Artifact Contract Families

### A) Online Data Plane Artifacts
Required families:
- Raw immutable event logs
- Canonical OHLCV outputs
- Data-plane digest manifests
- Revision metadata when late/corrected data occurs

Contract expectations:
- Raw and canonical artifacts are content-addressable.
- Canonical outputs must be reproducible from raw logs.
- Gap and late-data status must be explicitly encoded.

### B) Paper-Live Futures Artifacts
Required families:
- Run manifest
- Decision records
- Simulated orders/fills
- Position timeline
- Risk events
- Cost/funding breakdown
- Digest set for replay identity

Contract expectations:
- Artifacts represent runtime truth for evaluation.
- Risk and kill-switch events are explicit and queryable.
- Replay identity components are present and versioned.

### C) Research Loop Artifacts
Required families:
- Backtest summary set
- Walk-forward summary set
- Paper-live validation summary set
- Promotion verdict artifact
- Stop-condition audit artifact

Contract expectations:
- Promotion decisions are evidence-based and artifact-backed.
- Regime and cost sensitivity evidence is required for promotion.

## Determinism Rules
- Canonical serialization is stable and hashable.
- Input/config identity must be explicit in manifest artifacts.
- Re-run/replay parity is required for deterministic subsystems.
- Any unreconciled nondeterminism is treated as contract failure.

## Safety Rules
- Missing required artifacts => fail closed.
- Schema violations => fail closed.
- Digest mismatch => fail closed.
- Unknown revision lineage => fail closed.

## Related Specs
- `docs/02_ARCHITECTURE_BOUNDARIES.md`
- `docs/06_DATA_PLANE_ONLINE.md`
- `docs/07_PAPER_LIVE_FUTURES.md`
- `docs/08_RESEARCH_LOOP.md`
- `docs/09_EXECUTION_FUTURE.md`
