# Phase-6 Stage-4 Audit — User Extensibility Gate

## Validation Flow Diagram
```
user_indicators/<id>/indicator.yaml + indicator.py
user_strategies/<id>/strategy.yaml + strategy.py
                |
                v
   src.plugins.validate (CLI)
                |
                v
   src.plugins.validation
   - YAML schema + required fields
   - AST safety scan (imports/calls/attrs)
   - Global state checks
   - Runtime determinism checks
   - Warmup + NaN enforcement
                |
                v
artifacts/plugin_validation/<type>/<id>.json
artifacts/plugin_validation/index.json
                |
                v
src.plugins.registry (artifact-only)
                |
                v
API /plugins/active + /plugins/failed
                |
                v
UI selection lists + diagnostics (artifact-driven)
```

## Failure Scenarios (Fail-Closed)
- Missing required files (`indicator.yaml`, `indicator.py`, `strategy.yaml`, `strategy.py`).
- YAML parse error or schema mismatch (missing/unknown fields, invalid types/enums).
- Forbidden imports or calls (I/O, network, time, randomness, subprocess, eval/exec).
- Global mutable state or monkey-patching detected.
- Runtime errors during validation.
- Non-deterministic outputs for identical inputs.
- Warmup violations (early ENTER intents).
- NaN policy violations after warmup.
- Missing indicator dependencies referenced by a strategy.
- Missing/invalid validation artifact (treated as INVALID).

## Reproduce Pass/Fail
1. Create or edit plugin files under `user_indicators/<id>/` or `user_strategies/<id>/`.
2. Run validation:
```
python -m src.plugins.validate --out artifacts/plugin_validation
```
3. Inspect artifacts:
```
artifacts/plugin_validation/indicator/<id>.json
artifacts/plugin_validation/strategy/<id>.json
artifacts/plugin_validation/index.json
```
4. Run tests:
```
python -m pytest -q
```

## What Makes a Plugin Visible
- A plugin is visible only if its validation artifact has `status: "VALID"`.
- Missing or invalid artifacts are treated as `INVALID` (fail-closed).
- The UI and API read only validation artifacts and never re-run validation.

## Determinism Guarantees
- Static deny/allow rules prohibit time, randomness, I/O, subprocess, and dynamic execution.
- Runtime validation runs the plugin twice with identical inputs and compares outputs.
- Warmup rules are enforced before ENTER intents and before NaN-free outputs are required.
- Validation artifacts capture a source hash to detect changes.

## Security Model Summary
- Strict import allowlist with explicit forbidden roots (I/O, network, time, randomness).
- Forbidden calls include `eval`, `exec`, `compile`, `open`, `__import__`, `setattr`, `delattr`.
- Attribute access to dangerous builtins is rejected.
- Monkey-patching is detected via assignment to imported/bound module attributes.
- Path traversal protection rejects unsafe ids when reading artifacts.
- No execution of unvalidated plugins: loaders read artifacts only.

## CI/Linux Root Cause & Fix
- Symptom: On Ubuntu CI, runtime validation returned `RUNTIME_ERROR` instead of expected codes (e.g., `RUNTIME_TIMEOUT`, `INTENT_INVALID`).
- Evidence: CI run 21966156083 (CPU limit reverted) failed timeout tests with `RUNTIME_ERROR`; CI run 21966258386 (memory limit reverted) failed multiple runtime validation tests with `RUNTIME_ERROR`. Proof run: https://github.com/Buff-Trading-AI/Buff/actions/runs/21967997119 showed `RUNTIME_ERROR(exitcode=-9 (signal SIGKILL))`.
- Root cause: the worker was terminated before reporting results when `RLIMIT_CPU` matched the wall-time timeout or `RLIMIT_AS` was capped at 256MB; missing payloads surfaced as `RUNTIME_ERROR`.
- Minimal fix: keep `RLIMIT_CPU = ceil(timeout) + 1` and `RLIMIT_AS = 512MB`; use `multiprocessing.Pipe` for IPC (no private APIs); avoid global spawn start-method forcing; include exitcode/signal in `RUNTIME_ERROR` messages when no payload is received.
