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
