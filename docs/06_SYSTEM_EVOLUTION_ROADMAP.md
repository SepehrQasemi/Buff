# SYSTEM_EVOLUTION_ROADMAP

This document defines all possible future stages.
It does NOT determine current stage.
Current stage is defined exclusively in:
docs/PROJECT_STATE.md

---

## S0 - Deterministic Analysis Engine
Scope:
- File-based runs
- Deterministic evaluation
- Fail-closed enforcement
- Artifact generation

No execution.
No broker access.

---

## S1 - Observability & Run Intelligence
Scope:
- Run index
- Artifact registry
- Metrics exposure
- Queryable run metadata

---

## S2 - Multi-User Isolation Layer
Scope:
- User-scoped storage
- Run ownership boundaries
- Access control enforcement

---

## S3 - Controlled Execution Simulation
Scope:
- Execution simulation sandbox
- Strict runtime boundaries
- No real broker integration

---

## S4 - Risk Engine Maturity
Scope:
- Expanded risk semantics
- Stronger risk controls
- Explainable risk decisions

---

## Platform Observability & Productization
Stage token: `S6_PLATFORM_OBSERVABILITY_LAYER`

Scope:
- Platform-level observability and diagnostics expectations
- Product reliability and readiness signal hardening
- Clear evidence model for CI + runtime acceptance

Spec:
- [PLATFORM_OBSERVABILITY_AND_PRODUCTIZATION_SPEC.md](./stages/PLATFORM_OBSERVABILITY_AND_PRODUCTIZATION_SPEC.md)

---

## S7 - Personal Research Engine
Stage token candidate: `S7_PERSONAL_RESEARCH_ENGINE`

Scope:
- Deterministic experiment orchestration over S6 run artifacts
- Multi-run analysis and ranking for single-user research workflows
- Artifact-aware research assistant behavior (analysis only, no execution authority)

Architectural rationale:
- S6 already hardens deterministic run production, observability, and artifact integrity.
- S7 uses that stable foundation to add cross-run research capabilities without changing execution boundaries.

Why S7 follows S6:
- Experiment-level reliability depends on S6 guarantees for run determinism, read-only observability, and fail-closed contracts.
- Without S6, multi-run ranking and assistant insight quality would be unstable and non-reproducible.

Risk assessment:
- Primary risk: accidental scope creep into execution/broker/SaaS features.
- Primary control: preserve S6 safety boundaries and keep S7 strictly analysis/research-only.
- Secondary risk: nondeterministic experiment ordering or ranking drift.
- Secondary control: canonical experiment manifests, stable parameter ordering, and artifact-based recomputation.

Spec:
- [S7_PERSONAL_RESEARCH_ENGINE_SPEC.md](./stages/S7_PERSONAL_RESEARCH_ENGINE_SPEC.md)
- [RESEARCH_ARCHITECTURE.md](./research/RESEARCH_ARCHITECTURE.md)

## Future Layer - External Integration Layer
Scope:
- Broker adapters (strictly gated)
- Real execution boundaries
- Regulatory constraints
- Separate architecture boundary revision required
