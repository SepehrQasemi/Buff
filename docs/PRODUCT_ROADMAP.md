---
# Product Roadmap (Official)

## Product Identity

Canonical decisions: [Decisions (Canonical)](./DECISIONS.md)


**What Buff is**
Buff is a deterministic, artifact-first strategy research lab with a chart-first, read-only UI. It generates reproducible run artifacts from historical data and renders results without hidden recomputation.

**What Buff is not**
- Not a broker-connected trading terminal
- Not a live trading execution system
- Not a signal service
- Not a backdoor “recompute in UI” product

## Core Principles (Non-Negotiable)

1) **Read-only UI & assistant**  
The UI and assistant must never expose trading/execution controls.

2) **Artifact truth only**  
UI must render from produced artifacts. No hidden recomputation of metrics/signals/trades in the UI.

3) **Determinism & reproducibility**  
Given the same canonical inputs, the run id and artifacts must be identical.

4) **Fail-closed safety**  
When validation, plugins, registry, or risk checks fail, the system must fail closed with stable, user-explainable error codes.

5) **Single source of truth for user runs**  
User-created runs must live under a dedicated runs root directory with an atomic registry index. Demo/fixtures must not silently become a second truth source.

## Canonical User Outcome

A user can:
1) Create a run from CSV historical data + selected strategy + parameters
2) See the run appear in the run list
3) Open the run workspace and inspect chart, trades, metrics, and timeline — all rendered from artifacts

## Decisions (Locked)

### Data input in UI
UI run creation is **file-based** (user selects a CSV file).  
Implementation detail: the backend may store the file to a controlled location and reference it by an internal path in the run request, so existing request contracts can remain path-based while UX stays file-based.

**Current status**
Today the UI flow may be path-based while the product target is file-based input.
Until migration is complete, documentation must clearly label path-based behavior as temporary.
See `docs/DECISIONS.md` (D-001).

### Runs root requirement
User runs must be stored under a configured runs root directory (RUNS_ROOT).  
If missing or misconfigured, the system returns a stable error explaining how to fix it. The product must not silently fall back to demo/fixtures as a substitute for user runs. Demo/fixtures are only allowed when `DEMO_MODE=1` and must be clearly labeled.

### Demo/fixtures policy
Demo/fixtures may exist for tests and local demos, but must be explicitly labeled and must not be the default “truth source” for user runs.

## Evolution Layers

### Layer 1 — Core Stabilization
Goal: turn the current system into a stable, unambiguous product core.

Deliverables:
- Deterministic run creation (CLI + UI)
- Atomic registry under runs root
- Run listing reflects newly created runs
- Workspace page renders created runs from artifacts
- Clear, stable error model for common failures
- Local gates pass consistently

Exit criteria:
- A first-time user can create and open a run without manual file copying.
- No ambiguity in “where runs live” and “what the UI reads”.

### Layer 2 — Product Finalization
Goal: make the core usable by non-expert users on a local machine.

Deliverables:
- Single-command dev start documentation
- “First run in 10 minutes” guide
- Clear UI status and error recovery steps
- Exportable run summary/report artifacts

Exit criteria:
- A new user can install, create a run, and interpret results with minimal support.

### Layer 3 — Product Upgrades
Goal: extend capability without breaking core principles.

Examples:
- Compare multiple runs
- Tagging and run metadata diffs
- Report generation (PDF/MD) from artifacts
- Improved plugin authoring templates & validation tooling

Guardrail:
- No feature may violate the Core Principles section.

## Required Docs Links

- USER_JOURNEY.md
- ARCHITECTURE_BOUNDARIES.md
---





