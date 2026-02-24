ARCHIVED — NOT AUTHORITATIVE
Superseded by new documentation reset 2026-02-24.
Do not rely on this file for current stage or product direction.

# Documentation Audit Report

## Executive Summary

What is good:
- Boundary intent is clearly documented in multiple places: read-only UI, artifact-driven rendering, deterministic outputs, and fail-closed behavior.
- The repo has broad documentation coverage across product, API, risk, plugins, runbook, and roadmap topics.
- Several legacy phase docs are explicitly marked deprecated, which is a good cleanup signal.

What is broken:
- Documentation sprawl: 73 in-scope docs for core product behavior causes high navigation and maintenance cost.
- Single-source-of-truth drift exists (duplicate files, duplicated status blocks, and stale metadata statements).
- Contract drift exists across artifact requirements and error code/schema naming.
- Operational guidance is split across user runbook, diagnostics, and release docs, with overlapping commands.

Audit scope constraints:
- Only repository files were used.
- No file moves/renames/deletes were performed.
- Only `docs/DOCS_AUDIT_REPORT.md` was created in this pass.

## Snapshot & Scope

- Repo root: `C:\dev\Buff`
- Current branch: `main`
- In-scope documentation files inventoried: **73**

Keyword-cluster coverage (files containing the keyword):

| Keyword | Files |
| --- | ---: |
| `roadmap` | 5 |
| `phase` | 22 |
| `layer` | 13 |
| `contract` | 33 |
| `schema` | 30 |
| `error` | 24 |
| `artifacts` | 30 |
| `runs_root` | 8 |
| `determinism` | 18 |
| `plugins` | 5 |
| `ui` | 53 |
| `security` | 6 |

## Inventory

| Path | Size (bytes) | Last Commit | Last Commit Date | Last Commit Subject | Top Headings (H1/H2) |
| --- | ---: | --- | --- | --- | --- |
| ARCHITECTURE.md | 989 | cc623ce | 2026-02-01 | Docs/refresh spec 2026 02 (#75) | H1: L1: ARCHITECTURE - Buff<br>H2: L3: Planes; L22: Rules; L27: Interfaces; L34: References |
| CHANGELOG.md | 230 | 4ab2a04 | 2026-01-28 | chore: add governance and github hygiene files | H1: L1: Changelog<br>H2: L8: [Unreleased] |
| CODE_OF_CONDUCT.md | 1543 | 4ab2a04 | 2026-01-28 | chore: add governance and github hygiene files | H1: L1: Contributor Covenant Code of Conduct<br>H2: L3: Our Pledge; L10: Our Standards; L23: Enforcement Responsibilities; L26: Scope; L30: Enforcement; L34: Attribution |
| CONTRIBUTING.md | 904 | 760f911 | 2026-02-04 | docs(ui): polish local UI runbook and add api version signal | H1: L1: Contributing<br>H2: L3: Quick checks; L13: Red-lines (non-negotiable); L21: Adding indicators or rules (deterministic); L29: Safety reviews |
| DECISION_RECORD_SCHEMA.md | 682 | 0e414d8 | 2026-01-29 | Phase 0: docs alignment, safe execution core, UI sandbox authoring | H1: L1: DECISION_RECORD_SCHEMA<br>H2: L5: Required Fields; L23: Optional Fields; L27: Contract Goals |
| docs/_archive/placeholder.md | 251 | cc623ce | 2026-02-01 | Docs/refresh spec 2026 02 (#75) | H1: L1: Archived Placeholder (2026-02-01); L8: Docs<br>H2: None |
| docs/ARCHITECTURE_BOUNDARIES.md | 1195 | 396c7df | 2026-02-13 | docs: add roadmap, decisions, and delivery checklist (#170) | H1: L2: Architecture Boundaries (Non-Negotiable)<br>H2: L6: Read-only boundaries; L10: Artifact boundary; L14: Determinism boundary; L18: Safety boundary (fail-closed); L21: Plugins boundary; L26: Storage boundary; L31: Anti-goals |
| docs/artifacts.md | 2841 | 4e68d03 | 2026-02-14 | chore(layer1): close out core stabilization invariants (#171) | H1: L1: Artifacts (M1)<br>H2: L3: OHLCV Parquet Schema; L14: Partitioning Strategy; L20: Naming Conventions; L32: Timeframes; L40: Guarantees (M1); L51: Explicit Non-Goals (M1); L58: Layer-1 Run Artifacts (RUNS_ROOT) |
| docs/audit/main-protection-and-pr-only.md | 1381 | 6c8b92d | 2026-02-03 | feat(selector): deterministic selector contract + backward-compatible wrapper (issues #42/#92) (#108) | H1: L1: Main branch protection and PR-only policy<br>H2: L3: Policy statement; L6: Required checks (merge gates); L11: Workflow triggers; L15: Ruleset / branch protection configuration (main); L24: Implementation status; L28: Verification checklist |
| docs/chatbot.md | 1864 | 5ac3025 | 2026-02-08 | Align existing docs with phase-0 specs | H1: L1: Chatbot<br>H2: L5: Architecture; L12: Examples; L17: How to generate daily summary; L28: Non-capabilities |
| docs/CHATBOT_IMPLEMENTATION.md | 1565 | 13b833b | 2026-02-09 | Phase 4: Chatbot API + AI Chat wizard UI + integration tests (#141) | H1: L1: CHATBOT_IMPLEMENTATION<br>H2: L3: API Endpoints; L7: Request Example; L22: Response Shape; L38: Mode Behavior; L44: Fail-Closed Behavior; L50: UI Wiring |
| docs/CHATBOT_SPEC.md | 2511 | 9873e0e | 2026-02-08 | Add phase-0 product spec files | H1: L1: CHATBOT_SPEC â€” AI Assistant (Guide + Reviewer)<br>H2: L3: Purpose; L12: Modes; L32: Flow 1: Add Indicator; L50: Flow 2: Add Strategy; L68: Flow 3: Review Strategy/Indicator; L84: Flow 4: Troubleshoot Errors; L90: Non-negotiable Safety Rules; L97: â€œExact Stepsâ€ Requirement |
| docs/ci-backup.md | 2844 | a2104b0 | 2026-02-03 | chore(docs): add CI sanity note (#114) | H1: L5: CI Backup (Plan 2)<br>H2: L11: Required runner labels; L16: Required GitHub Secrets; L21: How to test the fallback; L24: Troubleshooting checklist; L41: Security notes; L45: Watchdog and sweep; L54: Operator scripts |
| docs/data_pipeline.md | 889 | cc623ce | 2026-02-01 | Docs/refresh spec 2026 02 (#75) | H1: L1: Data Pipeline (M1)<br>H2: L8: Run; L14: Artifacts; L19: Invariants |
| docs/data_quality_report.md | 1805 | 831f1e4 | 2026-02-02 | feat(data): finalize deterministic 1m data quality report | H1: L1: Data Quality Report (1m)<br>H2: L7: Scope; L12: Schema (stable, versioned); L39: Severity rules; L46: Determinism guarantee |
| docs/data_timeframes.md | 3573 | cc623ce | 2026-02-01 | Docs/refresh spec 2026 02 (#75) | H1: L1: Data Timeframes<br>H2: L6: Canonical Base Timeframe; L12: Supported Timeframes; L20: OHLCV Aggregation Rules (Resampling); L30: Candle Timestamp Convention; L36: Handling of Gaps; L43: Partial Windows; L49: Timezone Requirements; L56: Deterministic Constraints; L62: Implementation References |
| docs/DECISION_RECORD.md | 6644 | c38a1a3 | 2026-02-04 | docs/spec: unify contracts for replay/snapshot/migration | H1: L1: Decision Record (M7)<br>H2: L5: Schema (required fields); L44: Schema Versioning & Compatibility; L63: Canonical JSON rules; L74: Hashing rules; L89: Example; L104: Corruption Handling; L112: Risk replay semantics; L119: Migration (v1 -> v2 structural mapping) |
| docs/DECISIONS.md | 1150 | 4e68d03 | 2026-02-14 | chore(layer1): close out core stabilization invariants (#171) | H1: L2: Decisions (Canonical)<br>H2: L6: D-001 â€” UI data input is file-based; L12: D-002 â€” User runs have a single truth source; L17: D-003 â€” Core boundaries are non-negotiable |
| docs/DELIVERY_CHECKLIST.md | 4651 | 4e68d03 | 2026-02-14 | chore(layer1): close out core stabilization invariants (#171) | H1: L2: Delivery Checklist (Operational)<br>H2: L6: Preconditions; L11: Proof Set A â€” Clean repo and reproducible environment; L16: Proof Set B â€” Quality gates (must pass); L29: Proof Set C â€” Create a run and observe it end-to-end; L61: Proof Set D â€” Storage and registry invariants; L71: Proof Set E â€” Failure modes are user-explainable; L91: Documentation links |
| docs/feature-contract.md | 3469 | 6d8f887 | 2026-02-03 | M3/M5: Feature bundle contract + deterministic pipeline + strategy registry/selector (fail-closed) (#115) | H1: L1: Feature Contract<br>H2: L3: Purity; L7: Determinism; L14: Fail-Closed Semantics; L17: FeatureSpec schema; L45: Canonicalization + ordering; L54: Feature manifest (schema_version=2); L69: Feature bundle metadata (schema_version=1); L83: Error semantics (deterministic codes) |
| docs/features.md | 1486 | a3fc5cd | 2026-01-28 | Docs: update README and feature-engine contracts (M4.1/M4.2) (#8) | H1: L1: Feature Engine (M4.1 / M4.2)<br>H2: L5: Registry Structure; L14: Multi-Output Mapping Rules; L20: Warmup and NaN Policy; L25: Validity Metadata; L34: Presets |
| docs/FIRST_RUN.md | 2692 | b4b133c | 2026-02-15 | layer2(pr3): export artifact-only run report (#176) | H1: L1: First Run In 10 Minutes<br>H2: L6: Prerequisites (3 minutes); L32: Start The Dev Servers (1 minute); L51: Create Your First Run (3 minutes); L64: Export Report (1 minute); L74: CSV Requirements; L82: Optional: Real-Smoke Check (3 minutes); L92: Troubleshooting |
| docs/FUNDAMENTAL_RISK.md | 1104 | e4b8961 | 2026-01-30 | M4: Fundamental Risk Permission Layer (#32) | H1: None<br>H2: L3: Overview; L13: Paths; L19: CLI; L25: Notes |
| docs/goldens.md | 393 | a3fc5cd | 2026-01-28 | Docs: update README and feature-engine contracts (M4.1/M4.2) (#8) | H1: L1: Goldens<br>H2: L5: Purpose; L10: Rules |
| docs/INDICATOR_CONTRACT.md | 2343 | 68daa38 | 2026-02-13 | phase6(stage4): lock runtime guardrails + CI invariants (#167) | H1: L1: INDICATOR_CONTRACT â€” Built-in and User-defined Indicators<br>H2: L3: Purpose; L10: Indicator Definition; L15: Required Files (User Indicators); L20: indicator.yaml; L36: indicator.py Interface; L44: Causality Rules; L48: Validation Requirements; L56: Built-in Indicator Coverage (v1 expectation); L66: Canonical contract constants |
| docs/long_run_playbook.md | 867 | 1c2efe9 | 2026-01-30 | B7: add feed generator and run/report scripts for long-run paper audit | H1: L1: Long-run Playbook<br>H2: L5: 1) Generate a large feed; L11: 2) Run long paper harness (example: 6 hours); L23: 3) Generate audit summary; L31: 4) Acceptance criteria |
| docs/modes.md | 1146 | a3fc5cd | 2026-01-28 | Docs: update README and feature-engine contracts (M4.1/M4.2) (#8) | H1: L1: Modes: Manual vs System<br>H2: L3: Shared Layer; L10: Manual Analysis Mode; L17: System/Core Mode; L28: Runner Modes (Train vs Live) |
| docs/PHASE1_API_CONTRACTS.md | 5490 | 13b833b | 2026-02-09 | Phase 4: Chatbot API + AI Chat wizard UI + integration tests (#141) | H1: L1: Phase-1 Artifacts API Contracts (UI Core)<br>H2: L7: Metadata; L10: Phase-1 Invariants (Hard Lock); L16: UI Contract (Phase-1); L22: Base; L26: Endpoints; L105: Fail-Closed Behavior |
| docs/PHASE2_CLOSURE.md | 338 | 80fd515 | 2026-02-08 | docs: phase2 closure note (#139) | H1: L1: Phase-2 Closure<br>H2: None |
| docs/PHASE5_BACKLOG.md | 21708 | 154fec8 | 2026-02-10 | docs: update phase5 backlog status (#154) | H1: None<br>H2: None |
| docs/phase6/CONTRACTS.md | 6006 | 8ad1e94 | 2026-02-11 | docs(phase6): consolidate execution spec and contracts (#162) | H1: None<br>H2: L5: 1) Run Builder Contract (Stage 1); L115: 2) Data Contract (CSV MVP and Provider-Ready); L139: 3) Storage Contract; L166: 4) API Contract Additions for Phase-6; L197: Versioning and Compatibility |
| docs/phase6/GATES.md | 133 | 8ad1e94 | 2026-02-11 | docs(phase6): consolidate execution spec and contracts (#162) | H1: None<br>H2: None |
| docs/phase6/README.md | 3133 | d7d810b | 2026-02-13 | Phase-6 Stage-5 RC: demo pack, strict verification gate, and UI error mapping (#168) | H1: None<br>H2: L3: Purpose; L6: No-skip Rule; L9: Scope Boundary; L20: Stages; L30: Stage-5 Demo; L50: Single Source of Truth Gates; L62: References |
| docs/phase6/ROADMAP.md | 133 | 8ad1e94 | 2026-02-11 | docs(phase6): consolidate execution spec and contracts (#162) | H1: None<br>H2: None |
| docs/phase6/SCOPE.md | 133 | 8ad1e94 | 2026-02-11 | docs(phase6): consolidate execution spec and contracts (#162) | H1: None<br>H2: None |
| docs/phase6/SPEC.md | 12290 | 396c7df | 2026-02-13 | docs: add roadmap, decisions, and delivery checklist (#170) | H1: None<br>H2: L3: No-skip Rule; L6: Problem Statement; L9: Target Personas; L14: In-Scope; L21: Out-of-Scope; L28: Definitions; L39: Product Completion Definition; L50: Security and Privacy; L56: Acceptance Journeys; L66: Stage 1: Real Run Builder; L108: Stage 2: Durable Storage; L145: Stage 3: Real Data Ingestion; L184: Stage 4: Usable UX; L223: Stage 5: Reliability and Safety; L262: UX Requirements; L282: Dependencies and Milestone Demos |
| docs/phase6/STAGE4_AUDIT.md | 3942 | 68daa38 | 2026-02-13 | phase6(stage4): lock runtime guardrails + CI invariants (#167) | H1: L1: Phase-6 Stage-4 Audit â€” User Extensibility Gate<br>H2: L3: Validation Flow Diagram; L33: Failure Scenarios (Fail-Closed); L45: Reproduce Pass/Fail; L62: What Makes a Plugin Visible; L67: Determinism Guarantees; L73: Security Model Summary; L81: CI/Linux Root Cause & Fix |
| docs/phase6/STAGES.md | 133 | 8ad1e94 | 2026-02-11 | docs(phase6): consolidate execution spec and contracts (#162) | H1: None<br>H2: None |
| docs/phase6/UX.md | 133 | 8ad1e94 | 2026-02-11 | docs(phase6): consolidate execution spec and contracts (#162) | H1: None<br>H2: None |
| docs/PHASE6_USABLE_PRODUCT.md | 175 | 8ad1e94 | 2026-02-11 | docs(phase6): consolidate execution spec and contracts (#162) | H1: None<br>H2: None |
| docs/PR_release_gate.md | 1222 | 48e26b5 | 2026-02-11 | docs: finalize PR release gate formatting | H1: L1: Release Gate: local preflight + CI workflow (fail-closed, timed, reported)<br>H2: L3: Summary; L10: Local Usage; L17: CI; L25: Safety Properties; L34: Proof (local) |
| docs/PRODUCT_ROADMAP.md | 3958 | 4e68d03 | 2026-02-14 | chore(layer1): close out core stabilization invariants (#171) | H1: L2: Product Roadmap (Official)<br>H2: L4: Product Identity; L18: Core Principles (Non-Negotiable); L35: Canonical User Outcome; L42: Decisions (Locked); L60: Evolution Layers; L101: Required Docs Links |
| docs/PRODUCT_SPEC.md | 3606 | 396c7df | 2026-02-13 | docs: add roadmap, decisions, and delivery checklist (#170) | H1: None<br>H2: L3: Product Identity; L7: Roadmap Alignment; L16: Target User; L20: Core Value Proposition; L25: Scope (Product v1); L58: Explicit Non-goals; L64: Product Principles (Non-negotiable); L69: Definition of â€œUsableâ€ |
| docs/PROJECT_SPEC.md | 7238 | c38a1a3 | 2026-02-04 | docs/spec: unify contracts for replay/snapshot/migration | H1: L1: PROJECT_SPEC - Buff<br>H2: L7: Status Legend; L11: Canonical Data Rule (Non-Negotiable); L17: Determinism Guarantees (DONE); L29: Safety & Governance Model (DONE); L39: Current System Behavior; L89: Related Docs |
| docs/README.md | 1517 | 396c7df | 2026-02-13 | docs: add roadmap, decisions, and delivery checklist (#170) | H1: L1: Buff Phase-0 Product Specs<br>H2: L14: Roadmap & Identity; L22: Roadmap / Next |
| docs/REGIME_SEMANTICS.md | 1568 | 8803f0c | 2026-02-01 | M2.5: deterministic regime semantics and strategy-family gating (#73) | H1: None<br>H2: L5: Regimes (7); L14: Default thresholds (conservative, not optimized); L26: Fail-closed rules; L30: Adding a new regime safely; L37: Feature references |
| docs/release_gate.md | 1233 | 42096af | 2026-02-11 | docs: polish release gate docs and PR text | H1: L1: Release Gate (Local)<br>H2: L11: Checks; L17: Flags; L22: Outputs; L32: Troubleshooting |
| docs/release_precheck.md | 1748 | 42096af | 2026-02-11 | docs: polish release gate docs and PR text | H1: L1: Release Precheck (Local)<br>H2: L31: Notes; L40: Examples |
| docs/REPLAY.md | 3144 | c38a1a3 | 2026-02-04 | docs/spec: unify contracts for replay/snapshot/migration | H1: L1: Replay & Reproducibility (M7)<br>H2: L5: Snapshot format; L27: Replay equivalence; L47: CLI usage |
| docs/resampling.md | 1233 | 77fd099 | 2026-02-02 | feat(data): deterministic 1m resampling with no lookahead | H1: L1: Deterministic 1m Resampling<br>H2: L5: Input schema; L15: Window alignment; L25: Aggregation rules; L34: Completeness rule (no lookahead); L41: Determinism |
| docs/RISK_MODEL_SPEC.md | 2119 | 9873e0e | 2026-02-08 | Add phase-0 product spec files | H1: L1: RISK_MODEL_SPEC â€” Default + User-customizable Risk (5 levels)<br>H2: L3: Goal; L11: Two-layer Risk Model (Recommended); L29: Risk Levels (1..5); L48: Required UI Behavior; L55: Custom Risk Definition; L64: Minimum Artifact Requirements |
| docs/RISK_POLICY.md | 2034 | 5ac3025 | 2026-02-08 | Align existing docs with phase-0 specs | H1: L1: Risk Permission Layer (M4)<br>H2: L3: Purpose; L9: Inputs; L14: Derived Metrics; L18: Default Configuration; L30: Decision Rules; L44: Outputs; L51: Auditing |
| docs/selector-contract.md | 2103 | 6c8b92d | 2026-02-03 | feat(selector): deterministic selector contract + backward-compatible wrapper (issues #42/#92) (#108) | H1: L1: Selector Contract<br>H2: L3: Overview; L7: SelectorInput (schema_version=1); L22: SelectorOutput (schema_version=1); L31: Ordering + Tie-break rules; L39: Reason codes; L46: Error semantics; L62: Determinism guarantee |
| docs/selector.md | 2474 | bd0b8bc | 2026-01-30 | M5 hardening: clarify precedence, decouple records, improve defensive semantics | H1: L1: Selector (Menu-Based)<br>H2: L5: Inputs; L14: Output; L23: Risk precedence; L32: DEFENSIVE semantics; L36: Rule ordering (first match wins); L46: Example |
| docs/strategy-decision.md | 820 | 6d8f887 | 2026-02-03 | M3/M5: Feature bundle contract + deterministic pipeline + strategy registry/selector (fail-closed) (#115) | H1: None<br>H2: L3: Decision schema (schema_version=1); L21: Invariants |
| docs/STRATEGY_CONTRACT.md | 2748 | 9873e0e | 2026-02-08 | Add phase-0 product spec files | H1: L1: STRATEGY_CONTRACT â€” User-defined Strategies<br>H2: L3: Purpose; L10: Strategy Lifecycle; L17: Required Files; L24: strategy.yaml (Metadata + Params Schema); L41: strategy.py (Interface); L62: Determinism Rules (Non-negotiable); L70: Performance/Safety Limits; L75: Validation Requirements; L83: How UI Should Surface Strategies |
| docs/STRATEGY_GOVERNANCE.md | 1377 | 13b833b | 2026-02-09 | Phase 4: Chatbot API + AI Chat wizard UI + integration tests (#141) | H1: L1: STRATEGY_GOVERNANCE<br>H2: L3: Rules; L8: Strategy Contract; L13: Approval Workflow; L18: Phase-0 Load & Activation Gate (Non-negotiable) |
| docs/STRATEGY_LIBRARY.md | 15910 | 45317af | 2026-02-08 | Phase 2: Built-in Strategy Pack v1 (20 strategies + registry adapter + tests) (#138) | H1: L1: Strategy Library<br>H2: L6: sma_crossover (v1.0.0) â€” Trend; L17: ema_crossover (v1.0.0) â€” Trend; L28: donchian_breakout (v1.0.0) â€” Trend; L40: bollinger_breakout (v1.0.0) â€” Trend; L53: supertrend_trend_follow (v1.0.0) â€” Trend; L69: adx_filtered_breakout (v1.0.0) â€” Trend; L88: rsi_mean_reversion (v1.0.0) â€” Mean Reversion; L103: bollinger_reversion (v1.0.0) â€” Mean Reversion; L116: zscore_reversion (v1.0.0) â€” Mean Reversion; L129: keltner_reversion (v1.0.0) â€” Mean Reversion; L143: macd_momentum (v1.0.0) â€” Momentum; L158: roc_momentum (v1.0.0) â€” Momentum; L170: stochastic_momentum (v1.0.0) â€” Momentum; L187: atr_volatility_breakout (v1.0.0) â€” Volatility; L202: bb_keltner_squeeze_release (v1.0.0) â€” Volatility; L218: pivot_breakout (v1.0.0) â€” Structure; L231: sr_retest_rule_based (v1.0.0) â€” Structure; L244: time_based_exit_wrapper (v1.0.0) â€” Wrapper; L254: trailing_stop_wrapper (v1.0.0) â€” Wrapper; L264: fixed_rr_stop_target_wrapper (v1.0.0) â€” Wrapper |
| docs/STRATEGY_PACK_SPEC.md | 1882 | 9873e0e | 2026-02-08 | Add phase-0 product spec files | H1: L1: STRATEGY_PACK_SPEC â€” Built-in Strategy Catalog (20)<br>H2: L3: Goal; L10: Rules for Inclusion; L21: Categories and Initial List (20); L54: Standard Outputs (must be consistent); L63: Parameter Schema Conventions; L69: Testing Minimum |
| docs/UI_SPEC.md | 5593 | 396c7df | 2026-02-13 | docs: add roadmap, decisions, and delivery checklist (#170) | H1: None<br>H2: L3: North Star; L11: Run Creation UX (File-based); L25: Pages / Screens; L166: Data Sources for UI (Truth Sources); L175: Chart Requirements; L184: Minimal UX Requirements |
| docs/UNIFIED_PROJECT_SPEC.md | 11686 | 3e0f287 | 2026-02-08 | docs: remove duplicate specs and strip bidi unicode | H1: L1: UNIFIED_PROJECT_SPEC<br>H2: L3: Metadata; L7: Phase-0 Source of Truth; L15: Definition, Goals, Non-Goals; L22: Safety Principles + Invariants; L31: Planes + Boundaries; L37: Data Timeframes + Resampling; L46: MVP v0 (M1 + M3 Smoke Test); L54: Risk Policy Contract + Schema; L62: Control Plane (arming + kill switch); L67: Decision Records; L75: Snapshots + Replay; L85: CLI Entrypoints; L93: Quality Gates; L96: Phase-0 Status |
| docs/USER_EXTENSIBILITY.md | 5517 | 6630a6e | 2026-02-12 | Plugin Gate Hardening: fail-closed enforcement + TTL index lock + observability (#164) | H1: L1: User Extensibility Quickstart (Phase-3 MVP)<br>H2: L6: Folder Structure; L20: Strategy Minimal Skeleton; L60: Indicator Minimal Skeleton; L94: Required YAML Fields (Exact); L120: Validation (Fail-Closed); L198: Where Validation Shows Up; L205: Troubleshooting (Common Failures) |
| docs/USER_JOURNEY.md | 1953 | 396c7df | 2026-02-13 | docs: add roadmap, decisions, and delivery checklist (#170) | H1: L2: User Journey (Official)<br>H2: L6: Journey 1 â€” Create a run and inspect results; L35: Journey 2 â€” Reproduce the same run; L40: Journey 3 â€” Error recovery (must be user-explainable); L48: Notes on file-based data input |
| docs/VERIFY_PHASE1_DIAGNOSIS.md | 4876 | 9eb2704 | 2026-02-10 | docs: phase5 execution plan + verify gate note (#143) | H1: None<br>H2: None |
| docs/WIP_BRANCH_POLICY.md | 619 | e1cd15c | 2026-02-10 | docs: add WIP branch policy (do-not-merge rule) (#155) | H1: L1: WIP Branch Policy<br>H2: L6: Do-Not-Merge Rule; L11: Reviewer Checklist |
| EXECUTION_SAFETY.md | 1691 | 4bbc994 | 2026-02-03 | M6: paper execution trade logs and safe-state (#117) | H1: L1: EXECUTION_SAFETY<br>H2: L3: Idempotency; L23: Position State Machine; L27: Kill Switch; L31: API Failure Behavior; L35: Protective Exit; L38: Secrets Handling |
| GITHUB_SETTINGS_CHECKLIST.md | 646 | 3aad833 | 2026-01-30 | chore: make CI dependency install robust | H1: L1: GitHub Settings Checklist<br>H2: None |
| PROJECT_SCOPE.md | 1199 | 5ac3025 | 2026-02-08 | Align existing docs with phase-0 specs | H1: L1: PROJECT_SCOPE v1.0 - Buff<br>H2: L3: Goals; L11: Non-Goals; L19: Separation of Planes; L28: References |
| README.md | 15436 | d7d810b | 2026-02-13 | Phase-6 Stage-5 RC: demo pack, strict verification gate, and UI error mapping (#168) | H1: L1: Buff<br>H2: L4: Overview; L13: Phase-1 Status (COMPLETE); L30: Safety Principles; L39: Invariants & Non-goals; L59: Data Timeframe Canonicalization; L64: Documentation; L73: Product Specs; L77: Roadmap / Next; L83: Quickstart; L92: Local UI (Artifact Inspector); L154: Verify Phase-1; L293: Generate local artifacts; L301: MVP Smoke Test (M1 + M3); L328: Dependency Locking; L356: Quality Gates; L364: Release Preflight (Local); L372: Governance / Safety; L379: Control Plane (arming / kill switch); L393: Decision Record Schema v1.0; L402: Replay & Reproducibility (M7); L424: End-to-End Flow; L434: Done v1.0; L440: Modes; L450: Architecture; L462: Disclaimer; L467: Report Generator (M4.3); L481: Workspace Index (M4.4); L495: Buff Audit CLI (M4.6); L509: Chatbot Read-Only Artifact Navigator (M4.5) |
| RISK_POLICY.md | 124 | 3e0f287 | 2026-02-08 | docs: remove duplicate specs and strip bidi unicode | H1: L1: RISK_POLICY<br>H2: None |
| SECURITY.md | 478 | 4ab2a04 | 2026-01-28 | chore: add governance and github hygiene files | H1: L1: Security Policy<br>H2: L3: Reporting a Vulnerability; L9: Handling Secrets |
| STRATEGY_GOVERNANCE.md | 1377 | 23f2f88 | 2026-02-08 | docs: clarify load gate is fail-closed | H1: L1: STRATEGY_GOVERNANCE<br>H2: L3: Rules; L8: Strategy Contract; L13: Approval Workflow; L18: Phase-0 Load & Activation Gate (Non-negotiable) |
| tests/fixtures/README.md | 178 | 6d8f887 | 2026-02-03 | M3/M5: Feature bundle contract + deterministic pipeline + strategy registry/selector (fail-closed) (#115) | H1: None<br>H2: None |

## Conflicts / Single Source of Truth Violations

### 1) Exact Duplicate: Strategy Governance
- Topic: duplicate contract/governance doc in two locations.
- Involved files: `STRATEGY_GOVERNANCE.md`, `docs/STRATEGY_GOVERNANCE.md`.
- Evidence:
  - `STRATEGY_GOVERNANCE.md:18` ? "## Phase-0 Load & Activation Gate (Non-negotiable)"
  - `docs/STRATEGY_GOVERNANCE.md:18` ? "## Phase-0 Load & Activation Gate (Non-negotiable)"
  - `STRATEGY_GOVERNANCE.md:30` ? "This gate is fail-closed ... plugin is treated as invalid and excluded."
  - `docs/STRATEGY_GOVERNANCE.md:30` ? same sentence.
- Recommendation: **KEEP** `docs/STRATEGY_GOVERNANCE.md`; **DEPRECATE** root `STRATEGY_GOVERNANCE.md` (replace with 1-line pointer).

### 2) Roadmap/Status Duplication + Contradiction
- Topic: repeated status statements conflict with existing stage audit artifacts.
- Involved files: `docs/README.md`, `docs/phase6/README.md`, `docs/phase6/STAGE4_AUDIT.md`, `README.md`, `docs/PRODUCT_ROADMAP.md`.
- Evidence:
  - `docs/README.md:26` ? "Status line: ... phase6 state summary."
  - `docs/phase6/README.md:66` ? "Status line: phase6 state summary."
  - `docs/phase6/STAGE4_AUDIT.md:1` ? "Phase-6 Stage-4 Audit ? User Extensibility Gate"
  - `docs/phase6/README.md:57` ? "... verify_phase6_stage5.py --with-services"
- Recommendation: **KEEP** `docs/PRODUCT_ROADMAP.md` for layer roadmap and `docs/phase6/SPEC.md` for stage state; **MERGE** status into one source; **DEPRECATE** duplicated status banners.

### 3) Error Contract Drift (Schema + Code Naming)
- Topic: error payload shape and code naming diverge across contract docs.
- Involved files: `docs/PHASE1_API_CONTRACTS.md`, `docs/phase6/CONTRACTS.md`.
- Evidence:
  - `docs/PHASE1_API_CONTRACTS.md:115` ? "{ "code": ..., "message": ..., "details": {} }"
  - `docs/phase6/CONTRACTS.md:95` ? "- hint: optional string"
  - `docs/PHASE1_API_CONTRACTS.md:123` ? code uses "invalid_run_id".
  - `docs/phase6/CONTRACTS.md:100` ? code uses a legacy uppercase run-id naming style.
- Recommendation: **MERGE** into one canonical error contract registry; choose one canonical code namespace with explicit backward-compatible aliases.

### 4) Artifact Contract Drift (Required Set Mismatch)
- Topic: required run artifacts differ between contracts.
- Involved files: `docs/artifacts.md`, `docs/phase6/CONTRACTS.md`.
- Evidence:
  - `docs/phase6/CONTRACTS.md:51` ? "required output files list" (manifest, decisions, metrics, timeline).
  - `docs/phase6/CONTRACTS.md:57` ? "Optional files: trades.parquet, errors.jsonl ..."
  - `docs/artifacts.md:62` ? "Required artifacts:" includes config/equity/trades/ohlcv.
  - `docs/artifacts.md:67` ? "equity_curve.json"; `docs/artifacts.md:71` ? "ohlcv_*.jsonl".
- Recommendation: **KEEP** one canonical artifact contract table (required vs optional vs phase-specific) and **MOVE** all artifact lists to that table.

### 5) Spec Proliferation + Stale Metadata
- Topic: multiple top-level specs overlap and at least one contains stale branch metadata.
- Involved files: `docs/UNIFIED_PROJECT_SPEC.md`, `docs/PROJECT_SPEC.md`, `docs/PRODUCT_SPEC.md`.
- Evidence:
  - `docs/UNIFIED_PROJECT_SPEC.md:4` ? "Branch: feat/mvp-smoke."
  - `docs/UNIFIED_PROJECT_SPEC.md:5` ? refs `.git/refs/heads/feat/mvp-smoke`.
  - `docs/PROJECT_SPEC.md:1` ? separate project-wide spec document.
  - `docs/PRODUCT_SPEC.md:1` ? separate product spec document.
  - Snapshot conflict: current branch is `main`.
- Recommendation: **KEEP** product-level definition and boundaries; **MERGE/MOVE** implementation evidence matrices to appendices; **DEPRECATE** stale branch/commit-in-doc metadata.

### 6) Runbook vs Diagnosis Overlap
- Topic: operational commands duplicated across user runbook and one-off diagnosis report.
- Involved files: `docs/FIRST_RUN.md`, `docs/VERIFY_PHASE1_DIAGNOSIS.md`.
- Evidence:
  - `docs/FIRST_RUN.md:37` ? "dev_start.py command"
  - `docs/FIRST_RUN.md:87` ? "see runbook real-smoke gate"
  - `docs/VERIFY_PHASE1_DIAGNOSIS.md:5` ? verify command runtime claim.
  - `docs/VERIFY_PHASE1_DIAGNOSIS.md:78` ? conclusion about exit behavior.
- Recommendation: **KEEP** `docs/FIRST_RUN.md` as user-facing runbook; **MOVE** diagnosis doc under archive/incidents and link only from troubleshooting appendix.

## Doc Gaps

Inferred intended boundaries from current docs:
- Read-only UI and assistant boundaries are explicit (`docs/ARCHITECTURE_BOUNDARIES.md`, `docs/PRODUCT_SPEC.md`).
- Artifact-driven rendering and fail-closed behavior are repeatedly emphasized.
- Determinism is a recurring invariant across contracts and roadmap materials.

Gap list (what is missing or under-specified):

1) Layer 3 data engine / canonical store plan
- Why it matters: data reliability and deterministic replay depend on explicit storage evolution (partitioning, retention, compaction, migration policy).
- Proposed location: `docs/04_ROADMAP_AND_CHECKLIST.md` (scope/timeline) + `docs/03_CONTRACTS.md` (canonical store contract).

2) Layer 4 live simulation loop plan
- Why it matters: current docs discuss runs and paper execution pieces, but not an end-to-end simulation loop contract/state machine for staged rollout.
- Proposed location: `docs/04_ROADMAP_AND_CHECKLIST.md` with explicit DoD, guardrails, and verification gates.

3) Layer 5 risk engine plan
- Why it matters: risk policy exists, but roadmap-level migration from current model to production-grade risk engine is not staged in one place.
- Proposed location: `docs/04_ROADMAP_AND_CHECKLIST.md` + risk section in `docs/03_CONTRACTS.md` (inputs/outputs/reason codes/SLOs).

4) Layer 6 execution plan + safety boundaries
- Why it matters: execution safety docs exist, but no unified layer plan defining strict boundaries between paper execution, broker adapters, and UI prohibition surfaces.
- Proposed location: architecture boundary section in `docs/02_ARCHITECTURE_BOUNDARIES.md` and rollout plan in `docs/04_ROADMAP_AND_CHECKLIST.md`.

5) Observability/ops runbook unification (orchestrator, stop_services, ports, locks)
- Why it matters: operations guidance is spread across FIRST_RUN, diagnosis, release docs, and scripts; failure recovery paths are hard to discover.
- Proposed location: `docs/05_RUNBOOK_DEV_WORKFLOW.md` with a single troubleshooting matrix.

6) Extension/multi-user readiness boundaries
- Why it matters: non-goal statements mention multi-tenant exclusion, but future boundary conditions (namespace isolation, quotas, identity boundaries) are not documented.
- Proposed location: future-readiness subsection in `docs/02_ARCHITECTURE_BOUNDARIES.md` and roadmap milestones in `docs/04_ROADMAP_AND_CHECKLIST.md`.

## Proposed Clean Documentation Architecture (Minimal Canonical Set)

Target canonical docs (single source of truth):
1. `docs/01_PRODUCT_OVERVIEW_AND_JOURNEYS.md`
2. `docs/02_ARCHITECTURE_BOUNDARIES.md`
3. `docs/03_CONTRACTS_AND_SCHEMAS.md`
4. `docs/04_ROADMAP_AND_DELIVERY_CHECKLIST.md`
5. `docs/05_RUNBOOK_DEV_WORKFLOW.md`

Suggested tree:
```text
docs/
  01_PRODUCT_OVERVIEW_AND_JOURNEYS.md
  02_ARCHITECTURE_BOUNDARIES.md
  03_CONTRACTS_AND_SCHEMAS.md
  04_ROADMAP_AND_DELIVERY_CHECKLIST.md
  05_RUNBOOK_DEV_WORKFLOW.md
  appendix/
    API_REFERENCE.md
    RISK_DEEP_DIVE.md
    PLUGIN_AUTHORING_GUIDE.md
  _archive/
    incidents/
    deprecated/
```

### Migration Mapping (Current -> Target)

| Current File(s) | Target Canonical Doc | Action |
| --- | --- | --- |
| `README.md`, `docs/PRODUCT_SPEC.md`, `docs/USER_JOURNEY.md` | `docs/01_PRODUCT_OVERVIEW_AND_JOURNEYS.md` | **MERGE** |
| `docs/ARCHITECTURE_BOUNDARIES.md`, `ARCHITECTURE.md`, `PROJECT_SCOPE.md` | `docs/02_ARCHITECTURE_BOUNDARIES.md` | **MERGE** |
| `docs/PHASE1_API_CONTRACTS.md`, `docs/phase6/CONTRACTS.md`, `docs/artifacts.md`, `docs/STRATEGY_CONTRACT.md`, `docs/INDICATOR_CONTRACT.md`, `DECISION_RECORD_SCHEMA.md` | `docs/03_CONTRACTS_AND_SCHEMAS.md` (+ appendices) | **MERGE** |
| `docs/PRODUCT_ROADMAP.md`, `docs/DELIVERY_CHECKLIST.md`, `docs/phase6/SPEC.md`, `docs/phase6/STAGES.md`, `docs/PHASE5_BACKLOG.md` | `docs/04_ROADMAP_AND_DELIVERY_CHECKLIST.md` | **MERGE** |
| `docs/FIRST_RUN.md`, `docs/release_precheck.md`, `docs/release_gate.md`, `docs/VERIFY_PHASE1_DIAGNOSIS.md`, `docs/long_run_playbook.md` | `docs/05_RUNBOOK_DEV_WORKFLOW.md` | **MERGE/MOVE** |
| `STRATEGY_GOVERNANCE.md` (root duplicate) | `docs/STRATEGY_GOVERNANCE.md` | **DEPRECATE** root file |
| `docs/PHASE6_USABLE_PRODUCT.md`, `docs/phase6/ROADMAP.md` | Archive with pointer retained | **DEPRECATE** (already marked) |
| `docs/UNIFIED_PROJECT_SPEC.md` | Canonical docs + appendix evidence index | **MOVE** evidence, **DEPRECATE** stale metadata sections |

### Deprecation Notice Template

```md
# DEPRECATED

This document is deprecated as of YYYY-MM-DD.
Canonical source: `<TARGET_DOC_RELATIVE_PATH>`.

Reason: <one-line reason>. No new updates should be made here.
```

## Prioritized Refactor Plan (PR-sized)

### PR1 ? Canonical Skeleton + Status Freeze
Scope:
- Create the 5 canonical docs with TOCs and placeholder sections.
- Add a docs status matrix (one table) and remove duplicated status sentences elsewhere.
Acceptance checks:
- Exactly one authoritative status table exists.
- `rg -n "status text marker for phase6" docs` returns either zero or one intentional archived hit.

### PR2 ? Contract Unification
Scope:
- Consolidate error schema/code registry and artifact required/optional matrix.
- Add alias policy for legacy error codes.
Acceptance checks:
- One canonical error-code table exists.
- One canonical artifact matrix exists with phase annotations.
- No contradictory `invalid_run_id` vs legacy run-id naming guidance without alias notes.

### PR3 ? Runbook Consolidation
Scope:
- Merge FIRST_RUN, release precheck/gate snippets, and operational troubleshooting into one runbook.
- Move diagnosis writeups to `_archive/incidents`.
Acceptance checks:
- `docs/05_RUNBOOK_DEV_WORKFLOW.md` contains dev_start/verify/stop_services/ports/locks matrix.
- Incident docs are referenced only from troubleshooting appendix.

### PR4 ? Product/Architecture Narrative Consolidation
Scope:
- Merge product identity, journey, and boundaries into canonical docs 01 and 02.
- Keep root README concise and link-first.
Acceptance checks:
- No duplicated product identity blocks across >2 files.
- Root README links to canonical docs instead of repeating large spec blocks.

### PR5 ? Gap Fill for Layers 3?6 + Future Boundaries
Scope:
- Add explicit plans for data engine (L3), live simulation (L4), risk engine (L5), execution safety rollout (L6), and multi-user readiness boundaries.
Acceptance checks:
- Roadmap contains Layer 3/4/5/6 goals, DoD, and verification gates.
- Architecture boundaries include future extension constraints and non-goals.

## No-Changes Guarantee

This audit did not rename, move, or delete documentation files. The only file created in this step is:
- `docs/DOCS_AUDIT_REPORT.md`
