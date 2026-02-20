# ANALYSIS_LAYER_SPEC

## Objective
Define deterministic multi-run analytics for S7, extending S6 run outputs into experiment-level comparison and ranking insights.

## Required Metrics Beyond Current Run Summary

### Rolling Sharpe
- Rolling window risk-adjusted return measure.
- Must define fixed window size and annualization policy in analysis metadata.

### Rolling Drawdown
- Rolling max drawdown trace over fixed windows.
- Must be reproducible from run equity/return sequence artifacts.

### Return Distribution
- Bucketed return histogram plus summary moments.
- Bucket policy and boundary definitions must be explicit and fixed.

### Trade Duration Histogram
- Distribution of trade holding durations.
- Duration unit and bucket boundaries must be explicit.

### Win-Rate By Regime
- Win-rate segmented by regime labels present in artifacts/metadata.
- If regime labels are absent, analysis must emit an explicit unavailable status.

### Risk-Adjusted Ranking Score
- Composite score for cross-run ranking.
- Weighting and normalization policy must be versioned and explicit.

### Multi-Run Comparison Table
- N-run table with normalized metrics and ranking columns.
- Must include tie-break columns and artifact completeness indicators.

## Required Artifact Extensions (S7 Layer)
The analysis layer may introduce experiment-scoped artifacts while keeping S6 run artifacts unchanged:
- `analysis_summary.json`
- `analysis_distributions.json`
- `analysis_ranking.json`
- `analysis_compare_table.json`

Extension rules:
- These are additive and must not replace required S6 run artifacts.
- All derived values must include provenance fields referencing source run artifacts.

## Visualization Expectations (No UI Implementation)
- Analysis outputs must support:
  - line-series rendering for rolling metrics
  - histogram rendering for distributions and durations
  - tabular rendering for N-run comparison and ranking
- Visualization contracts are data-shape commitments only; no frontend implementation is implied here.

## Determinism And Quality Constraints
- Fixed windowing, bucketing, and normalization rules must be declared in artifact metadata.
- Aggregations must be stable across repeated execution with identical inputs.
- Missing source artifacts must fail closed with explicit error codes.
- Ranking must use deterministic tie-break logic.
- S6 guarantees remain intact: SIM_ONLY, no broker/live path, fail-closed contracts.

## See also
- [S7 Personal Research Engine Spec](../stages/S7_PERSONAL_RESEARCH_ENGINE_SPEC.md)
- [Research Architecture](./RESEARCH_ARCHITECTURE.md)
- [Experiment Engine Spec](./EXPERIMENT_ENGINE_SPEC.md)
- [Research Data Model](./RESEARCH_DATA_MODEL.md)
- [Chat Research Assistant Spec](./CHAT_RESEARCH_ASSISTANT_SPEC.md)
- [Research Roadmap](./RESEARCH_ROADMAP.md)
