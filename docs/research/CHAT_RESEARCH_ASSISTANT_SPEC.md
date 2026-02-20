# CHAT_RESEARCH_ASSISTANT_SPEC

## Objective
Define S7 chat behavior as an artifact-aware research assistant for deterministic analysis workflows.

## Core Principle
Chat must be artifact-aware. It may interpret only provided and validated artifacts, and must explicitly surface missing evidence.

## Input Contract

Required artifact inputs:
- `metrics.json`
- `trades.jsonl`
- `timeline.json`

Optional context:
- run manifest/provenance fields
- experiment ranking and comparison artifacts
- user-supplied hypothesis/tags/notes

## Required Capabilities
- Detect and explain likely high-drawdown causes from artifact evidence.
- Detect overfitting signals in multi-run outcomes and parameter sensitivity patterns.
- Suggest next parameter tests as bounded, evidence-based hypotheses.
- Compare multiple runs using artifact metrics, trade behavior, and timeline context.

## Response Contract
- Every substantive claim should reference an artifact field or explicit absence of one.
- Comparisons must identify which run IDs/candidates were evaluated.
- Recommendations must include uncertainty and validation caveats.
- If required artifacts are unavailable, assistant must fail closed with actionable missing-input guidance.

## Explicit Limitations
- No hallucinated market data.
- No fake PnL projections.
- No implied live deployment recommendation.
- No run or experiment mutation side effects.

## Determinism And Safety Constraints
- Same input artifact set should produce materially consistent analytical conclusions.
- Assistant must not bypass runtime validation boundaries.
- Assistant is analysis-only and not an execution controller.
- S6 SIM_ONLY and fail-closed guarantees remain authoritative.

## See also
- [S7 Personal Research Engine Spec](../stages/S7_PERSONAL_RESEARCH_ENGINE_SPEC.md)
- [Research Architecture](./RESEARCH_ARCHITECTURE.md)
- [Experiment Engine Spec](./EXPERIMENT_ENGINE_SPEC.md)
- [Analysis Layer Spec](./ANALYSIS_LAYER_SPEC.md)
- [Research Data Model](./RESEARCH_DATA_MODEL.md)
- [Research Roadmap](./RESEARCH_ROADMAP.md)
