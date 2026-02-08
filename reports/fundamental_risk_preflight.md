# Fundamental Risk Preflight (2026-01-30)

## 1.1 Project structure
- Root listing: see repo root (directories include src, knowledge, schemas, tests, reports)
- `src` dirs (depth<=3):
  - src/audit
  - src/buff
  - src/buff/data
  - src/buff/features
  - src/chatbot
  - src/control_plane
  - src/data
  - src/decision_records
  - src/execution
  - src/features
  - src/knowledge
  - src/manual
  - src/paper
  - src/reports
  - src/risk
  - src/sandbox
  - src/selector
  - src/strategies
  - src/strategies/engines
  - src/strategy_registry
  - src/ta
  - src/ta/indicators
  - src/ui
  - src/utils
  - src/workspaces
- `knowledge` files (depth<=2):
  - knowledge/glossary.md
  - knowledge/market_state_rules.yaml
  - knowledge/schema.yaml
  - knowledge/technical_rules.yaml
- `schemas` files (depth<=2):
  - schemas/data_quality.schema.json
  - schemas/risk_report.schema.json
- `tests` files (depth<=2):
  - tests/test_b7_reporting.py
  - tests/test_cli.py
  - tests/test_cli_metadata.py
  - tests/test_control_plane.py
  - tests/test_data_contracts.py
  - tests/test_decision_records_b1.py
  - tests/test_decision_record_schema.py
  - tests/test_e2e_audit_cli.py
  - tests/test_e2e_pipeline.py
  - tests/test_execution_core.py
  - tests/test_fault_injection_b3.py
  - tests/test_feature_runner_e2e.py
  - tests/test_goldens_exist.py
  - tests/test_goldens_sanity.py
  - tests/test_indicators_vs_goldens.py
  - tests/test_inputs_digest.py
  - tests/test_knowledge_rules.py
  - tests/test_long_run_b5.py
  - tests/test_m1_end_to_end_determinism.py
  - tests/test_m5_selector_profiles.py
  - tests/test_market_state_feed_b6.py
  - tests/test_market_state_rules.py
  - tests/test_mode_separation.py
  - tests/test_paper_runner_b4.py
  - tests/test_placeholder.py
  - tests/test_replay_b2.py
  - tests/test_report_schema.py
  - tests/test_resample.py
  - tests/test_risk_evaluator.py
  - tests/test_risk_policy.py
  - tests/test_risk_report_contract.py
  - tests/test_risk_report_guard.py
  - tests/test_risk_report_paths.py
  - tests/test_risk_report_schema.py
  - tests/test_risk_smoke_offline.py
  - tests/test_sandbox.py
  - tests/test_validate.py
  - tests/__init__.py

## 1.2 Name collision checks
- Existing `src/risk` package detected:
  - src/risk/evaluator.py
  - src/risk/policy.py
  - src/risk/report.py
  - src/risk/types.py
  - src/risk/__init__.py
- `RISK_POLICY` references:
  - docs/RISK_POLICY.md
- `risk_state` references found across src/tests/schemas (existing risk/report/engine usage).
- `permission` references found across src/tests/docs (existing risk permission layer).
- `decision_records` references found across src/tests/docs (existing decision records subsystem).

## 1.3 Implementation path decision
- New module path: `src/risk_fundamental/` (avoids collision with existing `src/risk`).
- Rules file path: `knowledge/fundamental_risk_rules.yaml` (no existing file detected).
- Report outputs will use `fundamental_risk_` prefix to avoid collisions.

## 1.4 Dependencies
- `pyproject.toml` includes `PyYAML`, `pytest` (dev) and `ruff` tool config.
- `pydantic` not present; plan to use `dataclasses` + manual validation.
- No new dependencies required.

## Existing vs New (No Conflict Table)
| Area | Existing | New (Planned) | Collision Avoidance |
|---|---|---|---|
| risk module | `src/risk/` already present | `src/risk_fundamental/` | Separate namespace prevents import/name collisions |
| knowledge rules | `knowledge/technical_rules.yaml`, `knowledge/market_state_rules.yaml` | `knowledge/fundamental_risk_rules.yaml`, `knowledge/fundamental_glossary.md` | New filenames, no overwrite |
| reports | `reports/data_quality.json` | `reports/fundamental_risk_preflight.md`, `reports/fundamental_risk_latest.json`, `reports/fundamental_risk_timeline.json` | New prefixed filenames |
| tests | Existing risk/report tests | New fundamental tests under `tests/` + fixture `tests/fixtures/` | New filenames; no overlap |
| docs | Existing policy docs | `docs/FUNDAMENTAL_RISK.md` | New filename |
