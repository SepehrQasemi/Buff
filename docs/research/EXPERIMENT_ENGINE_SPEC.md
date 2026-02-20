# EXPERIMENT_ENGINE_SPEC

## Objective
Specify a deterministic experiment engine that expands canonical parameter grids into reproducible run batches, links run artifacts, and produces experiment-level ranking outputs.

## Canonical Concepts

### experiment_id
- Type: string
- Purpose: stable identifier for one experiment definition.
- Determinism rule: derived from canonical experiment manifest digest unless explicitly user-specified and validated.

### experiment_manifest.json
Canonical source of truth for:
- experiment metadata (name, hypothesis, created_at_utc, schema_version)
- fixed run context (dataset_id, strategy_id, timeframe/symbol scope where applicable)
- canonical parameter grid
- ranking policy
- deterministic ordering policy

### experiment result registry
A deterministic registry that stores one record per generated candidate:
- candidate_id
- normalized parameter set
- submitted run_id
- run status
- error envelope (if failed)
- artifact linkage references

## Canonical Experiment Data Model

### experiment_manifest.json (logical schema)
- `schema_version`: string
- `experiment_id`: string
- `objective`: string
- `dataset_id`: string
- `strategy_id`: string
- `parameter_grid`: object
- `ranking_policy`: object
- `created_at_utc`: string
- `stage_token`: string

### parameter_grid model
- `dimensions`: ordered array of dimension specs
- each dimension:
  - `name`: string
  - `values`: ordered array of scalar values
  - optional bounds metadata for audit clarity

Expansion contract:
- Cartesian expansion order is deterministic.
- Dimension ordering is canonicalized.
- Value serialization uses canonical JSON representation.

### experiment_registry.json (logical schema)
- `schema_version`: string
- `experiment_id`: string
- `candidates`: ordered array of candidate entries

Candidate entry:
- `candidate_id`: string
- `params`: object
- `run_id`: string or null
- `status`: `PENDING|CREATED|RUNNING|COMPLETED|FAILED|SKIPPED`
- `error_code`: string or null
- `artifact_refs`: object (run-relative references)

## Batch Submission Flow
1. Validate and canonicalize experiment manifest.
2. Expand parameter grid deterministically into candidate list.
3. For each candidate, build canonical run request payload.
4. Submit candidate run through existing validated run creation contract.
5. Persist candidate status transitions in experiment registry.
6. Finalize experiment summary and ranking outputs from produced artifacts.

## Ranking Schema

### ranking.json (logical schema)
- `schema_version`: string
- `experiment_id`: string
- `ranking_metric`: string
- `tie_breakers`: ordered array of metric keys
- `rows`: ordered array

Ranking row:
- `rank`: integer
- `candidate_id`: string
- `run_id`: string
- `score`: number or fixed-point integer policy aligned to active contract
- `metrics_snapshot`: object

Determinism rule:
- Equal scores are resolved by explicit tie-breakers, then `candidate_id` lexical order.

## Artifact Linking Strategy
- Experiment records store references to run artifacts, not duplicated run payload copies.
- Linkage points to run-scoped canonical artifacts (`manifest`, `metrics`, `trades`, `timeline`).
- Experiment-level summaries are derivations over linked run artifacts and are reproducible.

## Failure Modes
- Invalid experiment manifest shape or unknown fields.
- Empty/invalid parameter dimension definitions.
- Candidate run creation failure due to invalid params.
- Missing or corrupted run artifacts for completed candidates.
- Ranking failure due to absent required metrics.

Failure handling:
- Fail closed at candidate level with explicit error envelope.
- Preserve completed candidate outputs when partial failures occur.
- Never silently skip invalid candidates.

## Determinism Contract
- Same canonical experiment manifest must produce:
  - same candidate expansion order
  - same candidate IDs
  - same run request payload set
  - same ranking order given identical artifact inputs
- Registry writes are append/update deterministic with stable field ordering.
- No external mutable dependency is allowed in ranking or candidate generation logic.
