# User Extensibility Quickstart (Phase-3 MVP)

This is a concise, contract-aligned quickstart for user strategies and indicators.
UI is fail-closed: only validated plugins (VALID) appear in selection lists.

## Hard Safety Constraints
- User extensibility MUST NOT include trade execution or order placement.
- User strategies and indicators MUST NOT access broker APIs.
- User logic MUST NOT bypass API validation or runtime contract enforcement.
- All user-provided logic MUST be evaluated through deterministic, sandboxed backend validation.
- All extensibility artifacts MUST conform to [03_CONTRACTS_AND_SCHEMAS.md](./03_CONTRACTS_AND_SCHEMAS.md).

## Folder Structure
```
user_strategies/<strategy_id>/
  strategy.yaml
  strategy.py
  README.md            # optional
  tests/test_strategy.py  # recommended

user_indicators/<indicator_id>/
  indicator.yaml
  indicator.py
  tests/test_indicator.py # recommended
```

## Strategy Minimal Skeleton
`user_strategies/my_strategy/strategy.yaml` (required fields only)
```yaml
id: my_strategy
name: "My Strategy"
version: "1.0.0"
author: "Your Name" # optional
category: trend
warmup_bars: 50
inputs:
  series: [close]       # required series: close/open/high/low/volume
  indicators: []        # required indicators by id
params:
  - name: threshold
    type: float
    default: 0.5
    min: 0.0
    max: 1.0
    description: "Signal threshold"
outputs:
  intents: [HOLD, ENTER_LONG, EXIT_LONG]
  provides_confidence: false
```

`user_strategies/my_strategy/strategy.py`
```python
def get_schema() -> dict:
    return {
        # should match strategy.yaml
    }

def on_bar(ctx) -> dict:
    # ctx provides OHLCV, indicator values, and params
    return {
        "intent": "HOLD",
        "confidence": 0.0,
        "tags": [],
    }
```

## Indicator Minimal Skeleton
`user_indicators/my_indicator/indicator.yaml` (required fields only)
```yaml
id: my_indicator
name: "My Indicator"
version: "1.0.0"
author: "Your Name" # optional
category: momentum
inputs: [close]          # required series list (e.g., close, high, low)
outputs: [value]         # output series names
params:
  - name: period
    type: int
    default: 14
    min: 1
    description: "Lookback period"
warmup_bars: 14
nan_policy: "propagate"  # propagate | fill | error
```

`user_indicators/my_indicator/indicator.py`
```python
def get_schema() -> dict:
    return {
        # should match indicator.yaml
    }

def compute(ctx) -> dict:
    # ctx provides input series up to current bar and params
    return {
        "value": 0.0,
    }
```

## Required YAML Fields (Exact)
These must match the contracts:

**Strategy (`docs/STRATEGY_CONTRACT.md`)**
- `id`
- `name`
- `version`
- `author` (optional)
- `category`
- `warmup_bars`
- `inputs`
- `params` (schema list: type, default, optional min/max/enum, description)
- `outputs` (`intents`, `provides_confidence`)

**Indicator (`docs/INDICATOR_CONTRACT.md`)**
- `id`
- `name`
- `version`
- `author` (optional)
- `category`
- `inputs`
- `outputs`
- `params` (schema list: type, default, optional min/max/enum, description)
- `warmup_bars`
- `nan_policy` (propagate | fill | error)

## Validation (Fail-Closed)
Run the validator to generate artifacts:
```
python -m src.plugins.validate --out artifacts/plugin_validation
```
Validation writes:
```
artifacts/plugin_validation/<type>/<id>.json
artifacts/plugin_validation/index.json
```
Only `status=VALID` plugins are selectable in the UI. Invalid plugins remain hidden.

Example VALID artifact (`artifacts/plugin_validation/indicator/demo.json`):
```json
{
  "plugin_type": "indicator",
  "id": "demo",
  "version": "1.0.0",
  "status": "VALID",
  "reason_codes": [],
  "reason_messages": [],
  "checked_at_utc": "2026-02-01T00:00:00Z",
  "source_hash": "sha256...",
  "name": "Demo",
  "category": "momentum"
}
```

Example INVALID artifact:
```json
{
  "plugin_type": "indicator",
  "id": "bad",
  "version": "1.0.0",
  "status": "INVALID",
  "reason_codes": ["SCHEMA_MISSING_FIELD:id", "FORBIDDEN_IMPORT:os"],
  "reason_messages": [
    "Missing required field 'id'.",
    "Import 'os' is not allowed."
  ],
  "checked_at_utc": "2026-02-01T00:00:00Z",
  "source_hash": "sha256..."
}
```

Reason codes are stable, machine-readable identifiers. Codes include:
- `MISSING_FILE:<filename>`
- `YAML_PARSE_ERROR`
- `AST_PARSE_ERROR`
- `AST_UNCERTAIN`
- `VALIDATION_EXCEPTION`
- `SCHEMA_MISSING_FIELD:<field>`
- `SCHEMA_UNKNOWN_FIELD:<field>`
- `INVALID_ENUM:<field>`
- `INVALID_TYPE:<field>`
- `FORBIDDEN_IMPORT:<module>`
- `FORBIDDEN_CALL:<name>`
- `FORBIDDEN_ATTRIBUTE:<name>`
- `NON_DETERMINISTIC_API:<name>`
- `GLOBAL_STATE_RISK`
- `SOURCE_HASH_ERROR`
- `ARTIFACT_WRITE_ERROR`
- `ARTIFACT_INVALID`
- `ARTIFACT_MISSING`
- `TOO_LARGE`

Operational notes:
- Validation artifacts and index rebuilds use a simple lock file (`artifacts/plugin_validation/.index.lock`).
  Locks include a UTC timestamp and expire after 120s; stale locks are cleared automatically.
  If the lock is held, rebuilds fail-closed and the API returns empty plugin lists until the lock is released.
- Plugin source size/complexity is capped; oversized sources are rejected with `TOO_LARGE`.

You can also run the full gate:
```
[runbook Phase-1 gate](./05_RUNBOOK_DEV_WORKFLOW.md#verification-gates)
```
Note: run without PowerShell piping to preserve exit codes.

## Where Validation Shows Up
- UI strategy/indicator dropdowns include only validated plugins (VALID).
- Diagnostics panel shows failed plugins and rule_id/message details.
- API endpoints (used by UI):
  - `/api/v1/plugins/active`
  - `/api/v1/plugins/failed`

## Troubleshooting (Common Failures)
- **Forbidden imports**: static validation rejects unsafe modules (I/O, network, subprocess).
- **Schema missing fields**: YAML missing required keys (see contracts).
- **Warmup not honored**: ENTER intents emitted before `warmup_bars` complete.
- **NaN policy violation** (indicators): `nan_policy` not respected after warmup.



