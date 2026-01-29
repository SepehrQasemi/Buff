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
