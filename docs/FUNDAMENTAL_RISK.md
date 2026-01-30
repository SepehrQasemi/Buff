# Fundamental Risk Permission Layer

## Overview
This module evaluates macro, onchain, and news snapshots against declarative YAML rules and
returns a deterministic permission state (`green`, `yellow`, `red`) plus audit-ready evidence.
It is offline-first and does not call external APIs in CI.

Key properties:
- Deterministic rule evaluation (no ML, no predictions).
- Fail-closed on missing data (never green with missing inputs).
- Outputs only permission/risk states and size multipliers.

## Paths
- Rules: `knowledge/fundamental_risk_rules.yaml`
- Glossary: `knowledge/fundamental_glossary.md`
- Engine: `src/risk_fundamental/engine.py`
- Artifacts: `reports/fundamental_risk_latest.json`, `reports/fundamental_risk_timeline.json`

## CLI
Example:
```
python -m src.risk_fundamental.cli --rules knowledge/fundamental_risk_rules.yaml --fixture tests/fixtures/fundamental_snapshots.json --at 2026-01-01T00:00:00Z
```

## Notes
- Snapshot providers are interface-only; the offline provider reads fixtures.
- The rule DSL supports `eq`, `gte`, `lte`, `gte_abs_diff`, `lte_abs_diff`, and `missing`.
