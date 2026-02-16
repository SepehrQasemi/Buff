# Roadmap And Delivery Checklist

## Stage Authority

The active project stage is determined exclusively by:
docs/PROJECT_STATE.md

This roadmap defines possible stages only.
It does NOT define the current stage.

## Table Of Contents
- [Current Status](#current-status)
- [Layers 1 To 6 Roadmap](#layers-1-to-6-roadmap)
- [Delivery Checklist](#delivery-checklist)
- [Historical Context Links](#historical-context-links)

## Current Status
Current status: Phase-1 is complete and green; roadmap execution continues through layered hardening with status tracked in this document.

## Layers 1 To 6 Roadmap
| Layer | Focus | Outcome |
| --- | --- | --- |
| Layer 1 | Core stabilization | Deterministic run creation and artifact truth |
| Layer 2 | Product finalization | First-run usability and report export baseline |
| Layer 3 | Data engine upgrades | Canonical store evolution and stronger data guarantees |
| Layer 4 | Live simulation loop | Controlled simulation lifecycle and replayability |
| Layer 5 | Risk engine maturity | Expanded risk semantics, controls, and explainability |
| Layer 6 | Execution safety boundaries | Hardened execution gating and strict interface boundaries |

## Delivery Checklist
- Keep UI and chatbot read-only for execution.
- Keep artifacts as source of truth.
- Keep fail-closed error semantics stable and documented.
- Keep deterministic outputs for identical canonical inputs.
- Keep pre-release verification gates green (`verify_phase1`, release gate, tests).

## Historical Context Links
These docs remain as context while consolidation is in progress:
- [PRODUCT_ROADMAP.md](./PRODUCT_ROADMAP.md)
- [DELIVERY_CHECKLIST.md](./DELIVERY_CHECKLIST.md)
- [phase6/README.md](./phase6/README.md)
- [phase6/SPEC.md](./phase6/SPEC.md)
