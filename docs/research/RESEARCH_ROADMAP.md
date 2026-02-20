# RESEARCH_ROADMAP

## Scope
S7 roadmap for a deterministic, single-user Personal Research Engine built on S6 foundations.

## Phase R1 - Experiment Engine

### Concrete Deliverables
- Canonical experiment manifest contract.
- Deterministic parameter grid expansion contract.
- Experiment registry with run linkage and candidate status tracking.
- Experiment-level ranking artifact schema (initial metric set).

### Definition Of Done
- Same experiment definition yields same candidate list and ordering.
- Candidate-to-run linkage is persisted and auditable.
- Partial failures are explicit and non-silent.
- Experiment outputs are reproducible from stored artifacts.

### Regression Constraints
- No changes to S6 SIM_ONLY enforcement.
- No broker/live execution path introduced.
- Existing run contracts remain valid and non-breaking.

## Phase R2 - Multi-Run Analytics

### Concrete Deliverables
- N-run comparison table schema and generation logic.
- Extended analysis metrics: rolling Sharpe/drawdown, distributions, duration histogram, regime win-rate.
- Deterministic ranking score with tie-break policy.

### Definition Of Done
- N-run comparison artifacts are generated deterministically.
- Ranking artifacts include explicit policy metadata and tie-break trace.
- Missing/invalid source artifacts fail closed with clear error signaling.

### Regression Constraints
- No weakening of fail-closed behavior.
- No mutation of canonical run artifacts for analysis convenience.
- No hidden dependency on external/non-local data sources.

## Phase R3 - Insight Automation

### Concrete Deliverables
- Artifact-aware research assistant mode specification and response contract enforcement.
- Standardized insight templates for drawdown diagnosis, overfitting checks, and next-test suggestions.
- Multi-run comparative explanation format with explicit evidence references.

### Definition Of Done
- Assistant responses are artifact-grounded and bounded by known inputs.
- Missing-evidence paths are explicit and non-hallucinatory.
- Insight outputs are consistent across repeated runs with identical inputs.

### Regression Constraints
- Assistant remains non-execution and non-mutating.
- No fake market data or projected PnL generation.
- S6 safety boundaries remain authoritative.

## Phase R4 - Research UX Polish

### Concrete Deliverables
- Cohesive research workflow definitions spanning experiment setup, ranking review, tagging, and note capture.
- Consistent terminology and schema alignment across docs/contracts.
- Reduced ambiguity in failure and recovery semantics for research workflows.

### Definition Of Done
- Golden-path research workflow is documented end-to-end.
- Contract docs are cross-linked and non-contradictory.
- Research memory and comparison semantics are clear for implementation.

### Regression Constraints
- No scope expansion into SaaS, cloud-only, or live trading features.
- No duplication of operational command authority outside runbook sources.
- No erosion of deterministic/reproducible guarantees.
