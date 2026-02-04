# Contributing

## Quick checks

```bash
ruff format .
ruff check .
pytest -q
```

Note: Do not paste UI "Undo" lines; include only real command outputs.

## Red-lines (non-negotiable)

- No price prediction
- No buy/sell signals
- No strategy invention or optimization
- Deterministic + auditable behavior must be preserved
- Fail-closed behavior must be preserved (especially in risk/execution/control)

## Adding indicators or rules (deterministic)

- Prefer pure functions with explicit inputs/outputs.
- Avoid network calls or time-based randomness in indicator logic.
- Ensure outputs are reproducible for the same inputs.
- Document parameters and default values.
- Add or update tests to cover edge cases and fail-closed behavior.

## Safety reviews

- Changes under `src/risk` or `src/execution` require a short safety impact note in the PR.
- Do not relax validation or allow silent fallbacks.
