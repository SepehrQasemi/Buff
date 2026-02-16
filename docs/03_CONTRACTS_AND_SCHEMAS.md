# Contracts And Schemas

## Table Of Contents
- [Canonical Error Schema](#canonical-error-schema)
- [Error Code Registry](#error-code-registry)
- [Artifact Contract Matrix](#artifact-contract-matrix)
- [Strategy And Plugin Contracts](#strategy-and-plugin-contracts)
- [Temporary Detailed References](#temporary-detailed-references)

## Canonical Error Schema
All fail-closed API responses should follow this envelope:

```json
{
  "code": "STRING_CODE",
  "message": "Human readable message",
  "details": {},
  "error": {
    "code": "STRING_CODE",
    "message": "Human readable message",
    "details": {}
  }
}
```

Notes:
- `code`, `message`, and `details` are required at top-level.
- Nested `error` mirrors top-level values for stable client handling.

## Error Code Registry
| Canonical Code | Alias Notes | Notes |
| --- | --- | --- |
| `RUNS_ROOT_UNSET` | none | Missing RUNS_ROOT configuration |
| `RUNS_ROOT_MISSING` | none | Configured path does not exist |
| `invalid_run_id` | legacy: `RUN_ID_INVALID` | Invalid run id format |
| `RUN_NOT_FOUND` | legacy: `run_not_found` | Requested run does not exist |
| `metrics_missing` | none | Missing `metrics.json` |
| `DATA_INVALID` | none | Invalid input payload or dataset |

## Artifact Contract Matrix
| Artifact | Required Core | Optional | Phase-Specific Notes |
| --- | --- | --- | --- |
| `manifest.json` | yes | no | Run metadata and references |
| `decision_records.jsonl` | yes | no | Decision-level audit trail |
| `metrics.json` | yes | no | Summary metrics for UI/reporting |
| `timeline.json` | yes | no | Timeline events |
| `trades.jsonl` | phase-dependent | yes | Required for trade panels and some reports |
| `equity_curve.json` | phase-dependent | yes | Required in Layer-1 UX/report flows |
| `ohlcv_*.jsonl` | phase-dependent | yes | Used for chart rendering/timeframe contexts |
| `errors.jsonl` | no | yes | Optional diagnostic stream |
| `report.md` | no | yes | Exported user-facing report |

## Strategy And Plugin Contracts
- Strategy contract authority: [STRATEGY_CONTRACT.md](./STRATEGY_CONTRACT.md)
- Indicator contract authority: [INDICATOR_CONTRACT.md](./INDICATOR_CONTRACT.md)
- Governance authority: [STRATEGY_GOVERNANCE.md](./STRATEGY_GOVERNANCE.md)
- User plugin quickstart: [USER_EXTENSIBILITY.md](./USER_EXTENSIBILITY.md)

## Temporary Detailed References
These documents remain active during consolidation:
- [PHASE1_API_CONTRACTS.md](./PHASE1_API_CONTRACTS.md)
- [phase6/CONTRACTS.md](./phase6/CONTRACTS.md)
- [artifacts.md](./artifacts.md)
