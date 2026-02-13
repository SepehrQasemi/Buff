---
# Delivery Checklist (Operational)

This checklist defines the proof required to claim the product core is complete and stable.

## Preconditions
- You are on the main branch and synced.
- Local environment has Python and Node installed.
- You can start API and UI locally.

## Proof Set A — Clean repo and reproducible environment
1) `git status -sb` shows a clean tree.
2) `python --version` and `node --version` are recorded.
3) Dependencies can be installed using the documented commands.

## Proof Set B — Quality gates (must pass)
Run these and record exit codes:
1) Verification with services
2) Strict release gate
3) Runs gate for deterministic creation/listing
4) UI smoke

Expected outcome:
- All commands exit with code 0.

## Proof Set C — Create a run and observe it end-to-end
### C1) Create via UI
1) Open the UI run creation page.
2) Provide CSV input (file-based target; temporary path-based acceptable only if documented).
3) Choose a strategy and parameters.
4) Create the run.

Proof:
- A run id is returned.
- The run appears in the run list endpoint.
- The workspace page opens successfully.

### C2) Create via CLI
1) Use CLI to create a run from the same inputs as the UI run.

Proof:
- The run id matches the UI run for identical canonical inputs (determinism).
- Re-running is idempotent (same run id, no duplication).

## Proof Set D — Storage and registry invariants
Proof requirements:
- User-created runs live under the runs root directory.
- Registry index updates are atomic (no partial entries).
- Partial runs do not appear in the run list.

## Proof Set E — Failure modes are user-explainable
Verify the UI and API surface clear messages for:
- Runs root missing/misconfigured
- CSV invalid/unreadable
- Strategy/indicator validation failure
- Run already exists (idempotent)
- API unreachable

## Documentation links
- Product Roadmap: `docs/PRODUCT_ROADMAP.md`
- Decisions: `docs/DECISIONS.md`
- User Journey: `docs/USER_JOURNEY.md`
- Architecture Boundaries: `docs/ARCHITECTURE_BOUNDARIES.md`
---

