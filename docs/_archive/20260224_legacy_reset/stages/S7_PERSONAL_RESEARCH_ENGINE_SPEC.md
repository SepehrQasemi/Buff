ARCHIVED — NOT AUTHORITATIVE
Superseded by new documentation reset 2026-02-24.
Do not rely on this file for current stage or product direction.

# S7_PERSONAL_RESEARCH_ENGINE_SPEC

Stage token candidate: `S7_PERSONAL_RESEARCH_ENGINE`  
Current stage remains `S6_PLATFORM_OBSERVABILITY_LAYER` and is authoritative in `docs/PROJECT_STATE.md`.

## Objective
Transform Buff from a single-run artifact system into a Personal Quant Research Lab.

S7 extends deterministic run-level analysis into experiment-level research workflows while preserving S6 safety and determinism boundaries.

## Explicit Non-Goals
- No live trading.
- No broker integration.
- No multi-user SaaS features.
- No cloud deployment requirements.

## Core Capability Blocks

### 1) Experiment Engine
- Define an experiment as a canonical parameterized batch over a fixed dataset and strategy surface.
- Generate deterministic run requests from a canonical parameter grid.
- Track experiment manifest, run linkage, statuses, and aggregate results.

### 2) Multi-Run Comparison
- Compare more than two runs at once.
- Provide consistent table-based comparison over artifact-derived metrics.
- Preserve explicit mismatch surfacing (symbol/timeframe/market scope differences).

### 3) Parameter Sweep
- Support grid-based parameter exploration.
- Preserve stable ordering and reproducible scheduling from canonicalized grid definitions.
- Keep failures visible per candidate while allowing partial experiment completion.

### 4) Portfolio-Level Analysis (Single-User Scope)
- Aggregate run outcomes into a single-user research portfolio view.
- Provide portfolio-level ranking/selection support without introducing execution authority.
- Keep analysis artifact-backed and reproducible from stored run outputs.

### 5) Research Tagging And Memory
- Attach tags and notes to experiments and runs.
- Store researcher context in deterministic, file-compatible records.
- Enable retrieval of prior experiments by hypothesis/theme/outcome tags.

### 6) Chat Research Assistant (Artifact-Aware)
- Analyze experiment and run artifacts only.
- Explain observed outcomes and compare alternatives with explicit artifact grounding.
- Suggest next test candidates without claiming guaranteed performance.

## Success Criteria
- User can define a parameter grid for an experiment.
- System runs a batch deterministically from canonical experiment input.
- Ranking table exists for experiment outcomes.
- User can compare N runs in one research view.
- Chat can analyze `metrics.json` and `trades.jsonl` (plus timeline context) for experiment/run insight.
- No regression to S6 guarantees:
  - SIM_ONLY boundary preserved.
  - No broker/live execution path.
  - Deterministic/fail-closed behavior remains enforced.
