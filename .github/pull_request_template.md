## Summary

## Why

## Test evidence (paste output)
```
```

Note: Do not paste UI "Undo" lines; include only real command outputs.

## Safety impact (required if touching /src/risk or /src/execution)

## Red-line checks
- [ ] No direct push to main
- [ ] ruff + pytest run locally
- [ ] No price prediction
- [ ] No buy/sell signals
- [ ] No strategy invention/optimization
- [ ] Deterministic + auditable behavior maintained
- [ ] Fail-closed behavior preserved (especially in risk/execution/control)
- [ ] ruff format --check . passed
- [ ] ruff check . passed
- [ ] pytest -q passed
- [ ] CI is green
