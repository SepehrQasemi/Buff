# RISK_MODEL_SPEC — Default + User-customizable Risk (5 levels)

## Goal
Risk is present in the product even though UI is execution-free.
Risk impacts:
- whether signals are allowed
- sizing recommendations (if shown)
- warnings and timeline events
- trade filtering in analysis (e.g., “blocked by risk”)

## Contract Alignment
- All numeric handling MUST align with deterministic backend policy.
- Validation errors MUST propagate as canonical error codes defined in [03_CONTRACTS_AND_SCHEMAS.md](./03_CONTRACTS_AND_SCHEMAS.md).
- This specification MUST NOT override runtime contract enforcement.

## Two-layer Risk Model (Recommended)
### Layer 1: Hard Safety Caps (Non-negotiable)
These are always enforced and cannot be disabled by user customization:
- max loss per day (absolute or %)
- max exposure (absolute or %)
- max position size
- max concurrent positions
- circuit breaker triggers (e.g., consecutive losses, volatility spikes)

### Layer 2: User Risk Policy (Customizable)
User can define additional rules that are stricter or smarter:
- volatility-adjusted risk
- confidence-based constraints
- time/session constraints
- custom scoring

User risk policy may only restrict or annotate; it must not bypass hard caps.

## Risk Levels (1..5)
Each level is a preset that sets default parameters for both layers.

Level 1 — Ultra Conservative
- smallest exposure caps, strict circuit breakers, conservative sizing

Level 2 — Conservative
- tighter caps than default, conservative thresholds

Level 3 — Balanced (Default)
- reasonable caps, standard circuit breakers

Level 4 — Aggressive
- higher caps within safe bounds, less strict triggers

Level 5 — Experimental
- highest caps still bounded by hard safety caps
- extra warnings and “experimental” label in UI

## Required UI Behavior
- Risk level selector must be visible in Strategy tab.
- When risk blocks an entry/exit, UI must show:
  - blocked reason
  - which rule triggered
  - whether it was hard cap or user policy

## Custom Risk Definition
Users can provide:
- `user_risk/<risk_id>/risk.yaml`
- `user_risk/<risk_id>/risk.py`
But the system must:
- validate schema
- enforce hard caps regardless
- sandbox execution (no I/O, no network, timeouts)

## Minimum Artifact Requirements
When risk blocks an action, artifacts must record:
- timestamp
- attempted intent
- risk verdict (ALLOW/BLOCK)
- rule id and reason
- risk level in effect

