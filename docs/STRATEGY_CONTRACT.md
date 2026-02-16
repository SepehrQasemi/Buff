# STRATEGY_CONTRACT — User-defined Strategies

## Contract Alignment
- All numeric handling MUST align with deterministic backend policy.
- Validation errors MUST propagate as canonical error codes defined in [03_CONTRACTS_AND_SCHEMAS.md#error-code-registry](./03_CONTRACTS_AND_SCHEMAS.md#error-code-registry).
- This specification is descriptive and MUST NOT override runtime contract enforcement.

## Purpose
Allow users to add strategies safely without breaking core integrity.
Strategies must be:
- deterministic
- side-effect free
- purely decision logic (no execution, no I/O)

## Strategy Lifecycle
A strategy is a plugin with:
- metadata (name, version, author)
- parameter schema
- code implementing required interface
- optional documentation

## Required Files
User strategy package directory:
- `user_strategies/<strategy_id>/strategy.yaml`
- `user_strategies/<strategy_id>/strategy.py`
- `user_strategies/<strategy_id>/README.md` (optional but recommended)
- `user_strategies/<strategy_id>/tests/test_strategy.py` (recommended)

## strategy.yaml (Metadata + Params Schema)
Must include:
- id: stable identifier (snake_case)
- name: display name
- version: semver (e.g., 1.0.0)
- author: optional
- category: trend/mr/momentum/volatility/structure/wrapper
- warmup_bars: integer
- inputs:
  - required series: close/open/high/low/volume
  - required indicators (by id)
- params schema:
  - list of parameters with type, default, optional min/max/enum, description
- outputs:
  - intents: list supported
  - provides_confidence: bool

## strategy.py (Interface)
The strategy code must implement:

- `def get_schema() -> dict`
  returns the parsed schema or parameters metadata (must match YAML).

- `def on_bar(ctx) -> dict`
  called on each bar.
  Input `ctx` provides:
  - current bar (OHLCV)
  - historical series up to current bar (no future)
  - indicators values (precomputed, causal)
  - params
  Must return a dict:
  - intent: one of HOLD/ENTER_LONG/ENTER_SHORT/EXIT_LONG/EXIT_SHORT
  - confidence: optional float 0..1
  - tags: optional list of strings

- `def on_finish(ctx) -> dict` (optional)
  finalize metadata or summary.

## Determinism Rules (Non-negotiable)
Strategies MUST NOT:
- use randomness (unless seeded and recorded — discouraged)
- use current time, network, filesystem I/O
- spawn subprocesses
- import unsafe modules (configurable deny-list)
- access any future data (no lookahead)

## Performance/Safety Limits
- on_bar execution time must be bounded (timeout per call)
- memory usage must be bounded
- exceptions must be caught and reported as strategy ERROR events (not silent)

## Validation Requirements
A strategy is considered loadable only if:
- schema is valid
- required inputs exist
- on_bar returns valid intent values
- warmup bars satisfied before producing ENTER intents
- no forbidden imports/operations detected (static checks)

## How UI Should Surface Strategies
- strategies appear in Strategy dropdown only after validation passes
- parameter forms are generated from schema
- errors show actionable guidance and link to chatbot help flow
