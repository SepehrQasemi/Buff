# Buff Product Status (Authoritative Snapshot)

## 1. Current Stage
- Authoritative stage token (from `docs/PROJECT_STATE.md`): `S5_EXECUTION_SAFETY_BOUNDARIES`.
- S5 guarantees: SIM_ONLY execution boundaries, deterministic artifact-driven behavior, fail-closed validation, no live trading paths, no broker execution paths.

## 2. What Is Fully Working
- Deterministic engine behavior for identical canonical inputs.
- Strategy execution through the existing simulation pipeline (SIM_ONLY).
- Data import flow and dataset manifesting.
- Run creation and run indexing/registry visibility.
- Run Explorer and run detail artifact rendering in the local UI.
- Status polling for run lifecycle monitoring.
- Report export via server-side endpoint.
- UI Journey runner is implemented with PASS criteria covering: navigation flow, run creation flow, terminal run state, evidence capture, and explicit failure on fatal banners.

## 3. Known Operational Risks
- Windows host bind mounts can be unstable in some Docker Desktop environments, leading to intermittent `RUNS_ROOT_NOT_WRITABLE` 503 responses.
- Local operation depends on Docker Desktop (Windows) or Docker Engine (Mac/Linux) being installed and running.
- Large dataset performance envelopes are not yet characterized.
- API container logs currently show NumPy/pyarrow ABI warnings; observed as non-blocking in current runs but tracked.

## 4. What Is Explicitly Out of Scope
- Live trading.
- Broker integration.
- Multi-tenant SaaS hosting.
- Distributed execution.

## 5. Immediate Next Stability Goals
- Storage reliability for local Docker environments.
- CI integration for the UI Journey runner.
- Readiness probe hardening for transient filesystem failures.
