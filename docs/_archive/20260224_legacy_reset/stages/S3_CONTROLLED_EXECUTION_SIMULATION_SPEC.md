ARCHIVED — NOT AUTHORITATIVE
Superseded by new documentation reset 2026-02-24.
Do not rely on this file for current stage or product direction.

# S3 Controlled Execution Simulation Spec

## Stage Authority
- Current stage identity is authoritative in [../PROJECT_STATE.md](../PROJECT_STATE.md).
- In this repository, `S3` means `S3_CONTROLLED_EXECUTION_SIMULATION`.
- This file is the authoritative S3 stage spec.
- `docs/phase6/*` is implementation history and must not be used as the authority for current global stage semantics.

## Purpose
S3 adds a simulation-only, event-driven execution core that:
- accepts canonical simulation requests
- produces deterministic simulation results and artifacts
- preserves fail-closed safety and isolation boundaries

## Non-goals
- Live broker/exchange execution.
- Order placement to external venues.
- Use of broker credentials in simulation runtime.
- Mutation of real balances or positions.

## Normative References
- Contracts and schemas: [../03_CONTRACTS_AND_SCHEMAS.md](../03_CONTRACTS_AND_SCHEMAS.md)
- Non-negotiable boundaries: [../02_ARCHITECTURE_BOUNDARIES.md](../02_ARCHITECTURE_BOUNDARIES.md)
- Current stage snapshot: [../PROJECT_STATE.md](../PROJECT_STATE.md)

## Terminology
- `SimulationRunRequest`: canonical input envelope for one simulation run.
- `SimulationRunResult`: canonical output envelope for one simulation run.
- `request_digest_sha256`: SHA-256 of canonical request bytes.
- `result_sha256`: SHA-256 of canonical result bytes.
- `simulation_run_id`: deterministic id derived from request digest.
- `Replay`: rerun of the same replay identity tuple.

## Replay Identity (Normative)
The unique replay identity tuple is:
1. `tenant_id`
2. `artifact_sha256`
3. `dataset_sha256`
4. `config_sha256` (SHA-256 of canonicalized `config`)
5. `seed`
6. `engine.name`
7. `engine.version`

Normative outcomes:
- `simulation_run_id` MUST be derived from `request_digest_sha256`.
- Two runs with identical replay identity tuple MUST produce identical required output digests.
- Replay success is defined as byte-identical values for `fills_sha256`, `metrics_sha256`, `event_log_sha256`, `report_sha256`, and `result_sha256`.

## Isolation And Tenancy Requirements
- Each run is namespaced by `tenant_id` from authenticated context.
- Canonical storage path: `<RUNS_ROOT>/<tenant_id>/simulations/<simulation_run_id>/`.
- Cross-tenant artifact reads MUST fail closed with `404 RUN_NOT_FOUND`.
- Any client-supplied tenant override MUST be rejected fail-closed.

## S3 Gate Registry (Normative Names)
All S3 gates MUST be required by release_gate strict profile once S3 implementation begins.

CI workflow wiring is future implementation work, but gate names and pass/fail criteria in this registry are final and must not change without a new decision record.

| Name | Purpose | Inputs | Pass Criteria | Fail Criteria | Enforcement Target |
| --- | --- | --- | --- | --- | --- |
| `s3_double_run_compare` | Detect nondeterminism for identical replay identity. | Same `SimulationRunRequest` executed twice on same `engine.version`. | Required digests from both runs are byte-identical. | Any required digest differs. | `release_gate --strict` required gate; `ci` required check (future wiring). |
| `s3_no_live_execution_path` | Prevent accidental live execution codepaths. | Simulation runtime source and dependency graph. | No broker/exchange order-placement path is reachable from simulation entrypoints. | Any reachable live execution path is detected. | `release_gate --strict` required gate; `ci` required check (future wiring). |
| `s3_cross_tenant_isolation` | Enforce tenant-scoped read/write isolation. | Multi-tenant test fixtures and artifact access tests. | Same-tenant access succeeds; cross-tenant access returns `404 RUN_NOT_FOUND`. | Any cross-tenant read/write is allowed. | `release_gate --strict` required gate; `ci` required check (future wiring). |
| `s3_input_digest_verification` | Ensure artifact/dataset inputs are integrity-checked before run start. | Request payload + referenced artifact/dataset bytes. | Runtime-computed hashes match request hashes before simulation begins. | Missing hash, malformed hash, or mismatch accepted. | `release_gate --strict` required gate; `ci` required check (future wiring). |
| `s3_no_network` | Block external network egress from simulation engine. | Simulation process execution under test harness. | Network calls are blocked; simulation completes from local inputs only. | Any outbound network call succeeds during simulation. | `release_gate --strict` required gate; `ci` required check (future wiring). |

## Event Sequence Integrity (Normative)
- `event_seq` starts at `1` and increments by exactly `+1` for every event in `fills` and `traces`.
- A missing sequence value marks the artifact as corrupted.
- Corrupted `event_seq` ordering MUST cause replay verification failure via `s3_double_run_compare` and `s3_input_digest_verification`.

## Threat To Guardrail To Gate Mapping
| Threat | Runtime Guardrail (Normative Runtime Requirement) | Gate(s) |
| --- | --- | --- |
| Nondeterministic clock source | Runtime accepts only `config.clock_source=dataset_event_time`; wall-clock access is rejected. | `s3_double_run_compare` |
| Random behavior without seed | Runtime allows stochastic branches only from request `seed`; unseeded RNG use is rejected. | `s3_double_run_compare` |
| Cross-tenant artifact access | Runtime resolves all reads/writes under authenticated `tenant_id` namespace only. | `s3_cross_tenant_isolation` |
| External data fetch or input hash mismatch | Runtime denies network egress and validates `artifact_sha256`/`dataset_sha256` before run start. | `s3_no_network`, `s3_input_digest_verification` |
| Live execution/broker path accidentally enabled | Runtime hard-locks execution mode to simulation-only and denies broker adapters. | `s3_no_live_execution_path` |

## Definition Of Done (S3)
- [ ] `SimulationRunRequest` and `SimulationRunResult` validate exactly against [../03_CONTRACTS_AND_SCHEMAS.md](../03_CONTRACTS_AND_SCHEMAS.md).
- [ ] `s3_double_run_compare` is PASS in `ci` and strict release gate.
- [ ] `s3_no_live_execution_path` is PASS in `ci` and strict release gate.
- [ ] `s3_cross_tenant_isolation` is PASS in `ci` and strict release gate.
- [ ] `s3_input_digest_verification` is PASS in `ci` and strict release gate.
- [ ] `s3_no_network` is PASS in `ci` and strict release gate.
