# Buff
[![CI](https://github.com/Buff-Trading-AI/Buff/actions/workflows/ci.yml/badge.svg)](https://github.com/Buff-Trading-AI/Buff/actions/workflows/ci.yml)

## Project State (Authoritative)

The active stage, objectives, and transition gates are defined exclusively in:
docs/PROJECT_STATE.md

All reasoning about project direction must begin from that file.
This README is a non-normative summary.

## Overview

Buff is a safety-first, artifact-driven crypto strategy analysis system.
Current stage details are authoritative in `docs/PROJECT_STATE.md`.

## Scope And Boundaries

Summary only (non-authoritative):
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
- Buff does not forecast future prices or claim directional certainty.
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

Use the canonical quickstart commands from:
- `docs/05_RUNBOOK_DEV_WORKFLOW.md#quickstart`

Run verification from:
- `docs/05_RUNBOOK_DEV_WORKFLOW.md#verification-gates`

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

