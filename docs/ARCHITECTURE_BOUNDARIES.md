---
# Architecture Boundaries (Non-Negotiable)

This document defines boundaries that must not be violated by future changes.

## Read-only boundaries
- UI must not contain buy/sell/execution controls.
- Assistant must not act as an execution controller.

## Artifact boundary
- UI renders from artifacts only.
- UI must not “recompute” trades/metrics/signals as a hidden source of truth.

## Determinism boundary
- The same canonical inputs must produce the same run id and artifacts.
- Any randomness must be explicitly controlled and documented.

## Safety boundary (fail-closed)
- On validation, registry, plugin, or risk failures, the system fails closed with stable error codes and user-readable messages.

## Plugins boundary
- Strategies and indicators must be deterministic and side-effect free.
- Indicators must be causal (no future leakage).
- Plugins must be validated before being surfaced in UI.

## Storage boundary
- User runs live under a runs root directory.
- Registry index updates must be atomic.
- Partial runs must not appear as valid runs.

## Anti-goals
- Broker integration / live execution
- Hidden recompute in UI
- Multiple silent truth sources for runs
---
