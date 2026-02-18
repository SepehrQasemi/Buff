---
# Decisions (Canonical)

This file records locked product decisions and their implementation status.
Global roadmap/status reference: [Current Status](./04_ROADMAP_AND_DELIVERY_CHECKLIST.md#current-status).

## D-001 — UI data input is file-based
**Decision:** Run creation in the UI is file-based (user selects a CSV file).  
**Rationale:** Better UX, avoids repo-relative paths, prepares for broader user base.  
**Implementation note:** Not fully implemented in UI; current flow may be path-based.  
**Migration plan:** Add an upload endpoint that stores the file to a controlled location and passes an internal path to the run creation request.

## D-002 — User runs have a single truth source
**Decision:** User-created runs are stored under the runs root directory and listed from its atomic registry.  
**Rationale:** Avoid multiple silent truth sources.  
**Implementation note:** RUNS_ROOT is the only truth source for runs and artifacts when configured. Demo/fixtures are only accessible when `DEMO_MODE=1`; no silent fallback to `ARTIFACTS_ROOT` is allowed.

## D-003 — Core boundaries are non-negotiable
**Decision:** Read-only UI/assistant, artifact truth only, determinism, fail-closed safety.  
**Rationale:** Prevent product drift.

## D-004 — S3 is simulation-only with deterministic replay gate
**Decision:** `S3_CONTROLLED_EXECUTION_SIMULATION` remains simulation-only, uses an event-driven execution core, and requires CI double-run digest comparison for determinism enforcement.  
**Rationale:** This blocks accidental live execution paths and makes nondeterminism detectable before merge.  
**Implementation note:** S3 contracts are defined in [03_CONTRACTS_AND_SCHEMAS.md](./03_CONTRACTS_AND_SCHEMAS.md) and stage-specific guardrails are defined in [stages/S3_CONTROLLED_EXECUTION_SIMULATION_SPEC.md](./stages/S3_CONTROLLED_EXECUTION_SIMULATION_SPEC.md). `phase6` paths are historical references only.

---
