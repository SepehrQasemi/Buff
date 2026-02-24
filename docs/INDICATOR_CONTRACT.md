# NOT AUTHORITATIVE — Compatibility Shim

Canonical documentation moved during the reset on 2026-02-24.
This file exists only for compatibility with legacy paths and automation checks.
Do not use this file to determine current stage, runtime behavior, or product direction.

## Canonical Redirect
- `docs/README.md`
- `docs/03_CONTRACTS_AND_SCHEMAS.md`
- `docs/08_RESEARCH_LOOP.md`

## Contract Alignment
Indicator and plugin contract authority is defined in canonical docs and runtime code.
This shim preserves legacy path compatibility only.

## Canonical Contract Constants
```yaml
ALLOWED_PARAM_TYPES: ["int", "float", "bool", "string", "enum"]
ALLOWED_NAN_POLICIES: ["propagate", "fill", "error"]
ALLOWED_INTENTS: ["HOLD", "ENTER_LONG", "ENTER_SHORT", "EXIT_LONG", "EXIT_SHORT"]
```
