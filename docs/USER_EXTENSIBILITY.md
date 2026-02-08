# User Extensibility (Phase-3 MVP)

## Where to Place Plugins
- Indicators: `user_indicators/<indicator_id>/indicator.yaml` + `user_indicators/<indicator_id>/indicator.py`
- Strategies: `user_strategies/<strategy_id>/strategy.yaml` + `user_strategies/<strategy_id>/strategy.py`

## Validation (Fail-Closed)
Run the validator to generate artifacts:

```
python -m src.plugins.validate --out artifacts/plugins
```

Validation writes `artifacts/plugins/<type>/<id>/validation.json` with PASS/FAIL.

## Visibility Rule
Only plugins with `status=PASS` are eligible for UI selection lists. Invalid plugins remain hidden and cannot be selected.
