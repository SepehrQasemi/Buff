# Architecture Boundaries

## Table Of Contents
- [System Boundaries And Safety Rules](#system-boundaries-and-safety-rules)
- [UI Read-Only Guarantees](#ui-read-only-guarantees)
- [Runtime Boundaries](#runtime-boundaries)
- [Extensibility Boundaries](#extensibility-boundaries)
- [Future Readiness Non-Goal](#future-readiness-non-goal)
- [Canonical Links](#canonical-links)

## System Boundaries And Safety Rules
- Interface plane (UI/chatbot) is read-only for execution.
- Core/data plane produces deterministic artifacts.
- Control plane governs arming, safety locks, and kill-switch behavior.
- Fail-closed policy applies when validation, registry, or artifact checks fail.

## UI Read-Only Guarantees
- No buy/sell controls in UI.
- No broker controls in UI.
- No hidden mutation paths through UI or chatbot endpoints.
- Artifact-driven rendering only.

## Runtime Boundaries
- No live trading execution in current scope.
- Run creation and analysis are local, deterministic, and bounded by contract checks.
- Missing prerequisites must return explicit error responses.

## Extensibility Boundaries
- Plugins must pass validation before becoming visible or selectable.
- Unsafe imports/calls and non-deterministic behavior are rejected.
- Validation artifacts are the source of truth for plugin visibility.

## Future Readiness Non-Goal
Multi-user tenancy is a non-goal for the current product phase.
Any future move toward multi-user support must define explicit identity, isolation, and quota boundaries before implementation.

## Canonical Links
- Product overview: [01_PRODUCT_OVERVIEW_AND_JOURNEYS.md](./01_PRODUCT_OVERVIEW_AND_JOURNEYS.md)
- Contracts: [03_CONTRACTS_AND_SCHEMAS.md](./03_CONTRACTS_AND_SCHEMAS.md)
- Roadmap and status: [04_ROADMAP_AND_DELIVERY_CHECKLIST.md](./04_ROADMAP_AND_DELIVERY_CHECKLIST.md)
- Existing detailed boundaries (temporary): [ARCHITECTURE_BOUNDARIES.md](./ARCHITECTURE_BOUNDARIES.md)
