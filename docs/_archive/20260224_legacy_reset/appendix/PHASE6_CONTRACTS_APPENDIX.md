ARCHIVED — NOT AUTHORITATIVE
Superseded by new documentation reset 2026-02-24.
Do not rely on this file for current stage or product direction.

# Appendix: Phase-6 Contracts (Historical Detailed Notes)

Historical source retained from `docs/phase6/CONTRACTS.md` before PR2 contract unification.
Canonical contracts now live in [../03_CONTRACTS_AND_SCHEMAS.md](../03_CONTRACTS_AND_SCHEMAS.md).

---

# Phase-6 Contracts

This document defines the execution contracts for Phase-6. All implementations must be deterministic and fail-closed.

## 1) Run Builder Contract (Stage 1)

### Inputs
A run creation request is a structured object (JSON or YAML) with these required fields:
- schema_version: string (semver), example "1.0.0"
- data_source:
  - type: "csv" (Stage 1)
  - path: local filesystem path to CSV
  - symbol: string, required (example "BTCUSDT")
  - timeframe: string, required ("1m" or a supported derived timeframe)
  - start_ts: optional ISO 8601 UTC or epoch ms
  - end_ts: optional ISO 8601 UTC or epoch ms
- strategy:
  - id: string, required (registered strategy id)
  - version: string, optional
- risk:
  - level: integer 1..5, required

Optional fields:
- run_id: string, if omitted it is computed deterministically
- name: string
- notes: string
- created_by: string
- seed: integer, default 0

### Validation Rules
- run_id must match ^[a-z0-9][a-z0-9_-]{2,63}$ if provided.
- timeframe must be supported by docs/data_timeframes.md and resampling.md.
- symbol must be uppercase alphanumeric (no spaces).
- start_ts < end_ts when both provided.
- CSV path must exist and be readable.
- strategy id must be registered and validated by existing contracts.
- risk.level must be in 1..5.

### Outputs
The builder must write a run directory under RUNS_ROOT:

RUNS_ROOT/
  <run_id>/
    manifest.json
    decision_records.jsonl
    metrics.json
    timeline.json
    artifacts/
      (optional additional artifacts)

Historical required files (legacy snapshot):
- manifest.json
- decision_records.jsonl
- metrics.json
- timeline.json

Optional files:
- trades.parquet
- errors.jsonl
- report.md and report_summary.json
- snapshots/ (replay artifacts)

The builder must also update the run registry/index described in the Storage Contract.

### manifest.json (Minimum Required Fields)
- schema_version: string (semver)
- run_id: string
- created_at: ISO 8601 UTC
- data:
  - source_type: "csv"
  - source_path: string
  - symbol: string
  - timeframe: string
  - start_ts: optional
  - end_ts: optional
  - canonical_timeframe: "1m"
- strategy:
  - id: string
  - version: optional
- risk:
  - level: integer
- artifacts:
  - decision_records: "decision_records.jsonl"
  - metrics: "metrics.json"
  - timeline: "timeline.json"
  - additional: optional list of artifact paths
- inputs_hash: string (sha256 of canonicalized inputs)
- builder_version: string

### Error Model
All failures must return a stable error object:
- code: string (stable, machine-readable)
- message: string (short, user-facing)
- details: optional object
- hint: optional string

Legacy code list snapshot:
- RUNS_ROOT_UNSET
- RUN_CONFIG_INVALID
- RUN_ID_INVALID
- DATA_SOURCE_NOT_FOUND
- DATA_INVALID
- STRATEGY_INVALID
- RISK_INVALID
- RUN_EXISTS
- ARTIFACTS_WRITE_FAILED
- REGISTRY_WRITE_FAILED

### Idempotency and Determinism
- If run_id is omitted, it must be derived from a canonical hash of inputs.
- Re-running with identical inputs must yield the same run_id and artifacts.
- If run_id exists and inputs_hash matches, the builder must return success without rewriting artifacts.
- If run_id exists and inputs_hash differs, the builder must fail with RUN_EXISTS.

## 2) Data Contract (CSV MVP and Provider-Ready)

### CSV Required Columns
- ts (UTC timestamp) or timestamp (mapped to ts)
- open
- high
- low
- close
- volume

### Timestamp Rules
- Timestamps must be UTC, ISO 8601 with Z or epoch milliseconds.
- Timestamps must be strictly increasing with no duplicates.
- Timestamps must align to minute boundaries for 1m inputs.

### Missing Data Policy
- Default policy is fail-closed on gaps or invalid rows.
- A caller may explicitly allow gaps via a flag (allow_gaps=true) which records gaps in a data quality report.
- Any repair or fill behavior must be explicit and recorded in the manifest.

### Resampling Rules
- Canonical ingest is 1m. All higher timeframes are deterministic resamples from 1m.
- Resampling rules must follow docs/data_timeframes.md and docs/resampling.md.

## 3) Storage Contract

### Roots and Semantics
- RUNS_ROOT is authoritative for all Phase-6 runs.
- ARTIFACTS_ROOT remains read-only for Phase-1 fixtures and legacy artifacts.
- If RUNS_ROOT is unset, run creation must fail with RUNS_ROOT_UNSET.

### Atomic Write Rules
- Run directories are written to a temp path then atomically renamed to <run_id>.
- The registry/index is written to a temp file then atomically replaced.
- Partial or corrupted runs must not appear in the registry.

### Registry/Index Format
RUNS_ROOT/index.json is the canonical registry:
- schema_version: string
- generated_at: ISO 8601 UTC
- runs: list of entries, each with:
  - run_id
  - created_at
  - symbol
  - timeframe
  - status (CREATED, FAILED)
  - manifest_path
  - artifacts_present: list of filenames

A human-readable index may be produced at RUNS_ROOT/index.md but is not authoritative.

## 4) API Contract Additions for Phase-6

### POST /api/v1/runs
Creates a run.

Request JSON (RunCreateRequest):
- schema_version
- data_source
- strategy
- risk
- optional run_id, name, notes

Response (201 or 202):
- run_id
- status (CREATED, QUEUED, RUNNING, FAILED)
- message
- links:
  - self: /api/v1/runs/{run_id}
  - ui: /runs/{run_id}

Errors use the error model defined above.

### GET /api/v1/runs
Lists runs (existing Phase-1 endpoint). Phase-6 requires that runs created under RUNS_ROOT appear in this list.

### GET /api/v1/runs/{run_id}
Returns run summary and artifact references. Must fail closed if required artifacts are missing.

### GET /api/v1/runs/{run_id}/status
Returns current status and last_updated timestamps for long-running runs.

## Versioning and Compatibility
- schema_version fields use semver.
- MAJOR bumps are breaking changes.
- MINOR bumps add optional fields; readers must ignore unknown fields.
- PATCH bumps clarify without changing shape.
- Phase-6 must remain backward-compatible with Phase-1 fixtures under ARTIFACTS_ROOT.
