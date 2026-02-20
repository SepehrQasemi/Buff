# RESEARCH_ARCHITECTURE

## Purpose
Define how S7 adds experiment-scale research capability on top of S6 deterministic run infrastructure without changing execution boundaries.

## System Layers

### S6 Foundation (Deterministic Run System)
- Canonical run creation and artifact generation.
- SIM_ONLY enforcement and fail-closed validation.
- Read-only observability and artifact export surfaces.

### Experiment Layer
- Canonical experiment definition and parameter grid expansion.
- Deterministic batch run request generation.
- Experiment-level manifest and result registry management.

### Analysis Layer
- Multi-run metric aggregation and ranking.
- Extended research metrics (rolling, distributional, duration, regime-aware).
- Comparison outputs for N-run research decisions.

### Research Memory Layer
- Persistent, file-compatible experiment metadata, tags, notes, and run linkage.
- Single-user scoped research history for retrieval and iteration.

### Chat Insight Layer
- Artifact-aware assistant mode for explanation, comparison, and next-test suggestions.
- Analysis-only behavior with explicit uncertainty/failure signaling.

## Interaction Diagram (Textual)
1. Researcher defines experiment scope and parameter grid.
2. Experiment Layer canonicalizes grid and creates experiment manifest.
3. Experiment Layer emits deterministic run request set.
4. S6 Foundation executes each run and writes canonical run artifacts.
5. Experiment Layer links produced run IDs to experiment registry entries.
6. Analysis Layer computes aggregate/ranking outputs from run artifacts.
7. Research Memory Layer stores tags, notes, and decision context.
8. Chat Insight Layer consumes run/experiment artifacts and returns artifact-grounded analysis.

Flow view:
`Researcher -> Experiment Layer -> S6 Foundation -> Run Artifacts -> Analysis Layer -> Research Memory -> Chat Insight`

## Data Flow

### Run Artifact Inputs (from S6)
- `manifest.json`
- `metrics.json`
- `trades.jsonl` (or parquet variant when present)
- `timeline.json`
- `decision_records.jsonl`

### Experiment Aggregate Outputs (S7)
- Experiment manifest (canonical definition).
- Experiment run registry (candidate params, run_id, status, errors).
- Ranking table and analysis summaries derived from run artifacts.
- Research memory records (tags/notes/hypotheses).

## Determinism Preservation Strategy
- Canonical experiment manifests with stable key ordering and explicit schema versioning.
- Stable parameter grid expansion order independent of input key order.
- Deterministic run candidate IDs derived from canonical candidate payload.
- Ranking with explicit deterministic tie-break rules.
- Artifact-only analysis (no hidden recomputation from external sources).
- Fail-closed handling for missing/invalid artifacts at both run and experiment layers.

## S7 Boundary Constraints
- No live execution authority.
- No broker adapters.
- No multi-tenant SaaS assumptions.
- No cloud dependency requirement for core S7 behavior.
