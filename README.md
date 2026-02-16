# Buff
[![CI](https://github.com/Buff-Trading-AI/Buff/actions/workflows/ci.yml/badge.svg)](https://github.com/Buff-Trading-AI/Buff/actions/workflows/ci.yml)

## Overview

Buff is a safety-first, artifact-driven crypto strategy analysis system.
Phase-0 scope is read-only analysis UX and deterministic run artifacts.

## Scope And Boundaries

- Read-only UI: no buy/sell controls, no broker execution actions.
- Fail-closed behavior on missing/invalid inputs.
- Deterministic outputs from artifact inputs.
- Live execution is out of current product scope.

## Invariants & Non-goals

Invariants:
- Deterministic outputs for the same canonical inputs.
- Read-only UI and API boundaries for execution.
- Fail-closed behavior for invalid inputs and missing artifacts.

Non-goals:
- No prediction.
- Live broker execution in current scope.
- Strategy invention in UI.
- Multi-tenant hosted accounts in current scope.

Architecture and boundary rules:
- `docs/02_ARCHITECTURE_BOUNDARIES.md`

Error and artifact contracts:
- `docs/03_CONTRACTS_AND_SCHEMAS.md`

Roadmap and current status:
- `docs/04_ROADMAP_AND_DELIVERY_CHECKLIST.md#current-status`

## Quickstart

```bash
python -m pip install -e ".[dev]"
npm --prefix apps/web install
python scripts/verify_phase1.py --with-services --real-smoke
```

For full run/verify/recover workflows, use the canonical runbook:
- `docs/05_RUNBOOK_DEV_WORKFLOW.md`

## Docs (Canonical)

- `docs/01_PRODUCT_OVERVIEW_AND_JOURNEYS.md`
- `docs/02_ARCHITECTURE_BOUNDARIES.md`
- `docs/03_CONTRACTS_AND_SCHEMAS.md`
- `docs/04_ROADMAP_AND_DELIVERY_CHECKLIST.md`
- `docs/05_RUNBOOK_DEV_WORKFLOW.md`

## Specs Index

- `docs/README.md`

## Governance

- `SECURITY.md`
- `GITHUB_SETTINGS_CHECKLIST.md`
