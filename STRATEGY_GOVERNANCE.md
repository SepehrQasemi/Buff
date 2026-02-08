# STRATEGY_GOVERNANCE

## Rules
- Strategies are user-defined but must be versioned, registered, and tested.
- Selector may only choose from registered strategies.
- Any strategy change requires a version bump and changelog entry.

## Strategy Contract
- Deterministic behavior only
- Explicit inputs and outputs
- Output is intent only: LONG/SHORT/FLAT

## Approval Workflow
- Sandbox authoring -> review -> approved registry
- Live execution requires approved strategy_id
Phase-0 product scope is read-only; execution governance applies to future execution paths.

## Phase-0 Load & Activation Gate (Non-negotiable)

User-defined strategies and indicators MUST NOT appear in the UI, run in analysis, or be available for selection unless:

1) All required contract files exist (`strategy.yaml` + `strategy.py` for strategies; `indicator.yaml` + `indicator.py` for indicators).
2) Schema validation passes.
3) Static safety checks pass (no forbidden imports/operations).
4) Determinism checks pass (no randomness, no time access, no I/O).
5) Warmup and NaN policies are declared and validated.
6) A validation artifact (or status record) is written and stored.

If any check fails, the item remains inactive and is not visible to users in selection lists.
This gate is fail-closed: if validation cannot be completed successfully, the plugin is treated as invalid and excluded.
