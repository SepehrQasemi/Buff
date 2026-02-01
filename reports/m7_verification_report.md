# M7 Verification Report

Branch: m6-invariant-guardrails
Commit: dec5b6e6f63774c5e3c0f1e9b4937a9a3a6d4b1f
Date: 2026-02-01

## Command Outputs

### git fetch origin --prune
```
From https://github.com/Buff-Trading-AI/Buff
 - [deleted]         (none)     -> origin/m6-audit-bundle
 - [deleted]         (none)     -> origin/m6-audit-run
 - [deleted]         (none)     -> origin/m6-audit-verify
 - [deleted]         (none)     -> origin/m6-idempotency-diagnostics
 - [deleted]         (none)     -> origin/m6-idempotency-inflight
 - [deleted]         (none)     -> origin/m6-idempotency-persistence
 - [deleted]         (none)     -> origin/m6-idempotency-recovery
 - [deleted]         (none)     -> origin/m6-invariant-guardrails
   fdaf08e..9a31f47  main       -> origin/main
```

### git branch -vv
```
  archive/wip-local-dirty-backup-34           d346b0c WIP: local dirty changes (backup)
  b1-decision-records-jsonl                   fcc9133 [origin/b1-decision-records-jsonl: gone] B1: add decision_records JSONL schema and writer
  b2-replay-runner                            8d8ba48 [origin/b2-replay-runner: gone] B2: add replay runner to verify decision determinism
  b3-fault-injection                          b2f1e5b [origin/b3-fault-injection: gone] B3: add fault injection tests for decision_records and replay robustness
  b4-paper-runner-smoke                       6f887a2 [origin/b4-paper-runner-smoke: gone] B4: add paper runner smoke pipeline with restart and replay check
  b5-longrun-paper-harness                    cedbca2 [origin/b5-longrun-paper-harness: gone] B5: add long-run paper harness with rotation and periodic replay checks
  b6-market-state-feed                        39d3040 [origin/b6-market-state-feed: gone] B6: add market_state feed reader for long-run paper harness
  b7-longrun-reporting                        1c2efe9 [origin/b7-longrun-reporting: gone] B7: add feed generator and run/report scripts for long-run paper audit
  chore/ci-populate-checks                    02ccbfa [origin/chore/ci-populate-checks] chore: populate CI checks
  chore/ci-register-checks                    329672f [origin/chore/ci-register-checks: gone] chore(ci): publish legacy status context for rulesets
  chore/github-governance                     b3328b4 [origin/chore/github-governance: gone] chore: fix pandas 3.0 time freq aliases
  chore/governance-pack                       3ed60c2 [origin/chore/governance-pack: gone] fix: robust milestone title matching
  core-next                                   3f3e3bb M5 hardening: clarify precedence, decouple records, improve defensive semantics
  feat/buff-audit-cli                         71059fb [origin/feat/buff-audit-cli: gone] chore: centralize run_id sanitizer and harden CLI errors
  feat/chatbot-artifact-navigator             10fe3e4 [origin/feat/chatbot-artifact-navigator: gone] fix: always return index path when available
  feat/control-plane-execution-skeleton       66c464e [origin/feat/control-plane-execution-skeleton: gone] feat: add control plane, strategy registry, paper execution skeleton, and e2e tests
  feat/decision-record-contract-hardening     a20e2c6 [origin/feat/decision-record-contract-hardening: gone] chore: fix lint in paper engine test
  feat/golden-workspaces-e2e                  e8d04de [origin/feat/golden-workspaces-e2e: gone] test: add golden workspace fixtures and e2e audit CLI verification
  feat/report-generator                       db4287c [origin/feat/report-generator: gone] chore: ignore temp report artifacts and clarify report paths
  feat/workspace-index                        c31974f [origin/feat/workspace-index: gone] fix: clean workspace index output paths
  fix-packaging-risk-fundamental-imports      e4b8961 M4: Fundamental Risk Permission Layer (#32)
  fix/ci-stabilize                            523de24 [origin/fix/ci-stabilize: gone] chore: apply ruff formatting
+ fundamental-risk-wip                        4ffa30d (C:/Users/Sepehr/Desktop/buff-fundamental) [origin/fundamental-risk-wip: gone] CI: make src imports reliable for fundamental tests
  m2-technical-rules-v2                       94c65d4 [origin/m2-technical-rules-v2: gone] tests: make knowledge rules contract-based
  m3-market-state-multitimeframe              3f6c5ed [origin/m3-market-state-multitimeframe: gone] M5: add 3 engines, 10 strategy profiles, deterministic selector with explainability
  m4-risk-inputs-contract                     54efa23 [origin/m4-risk-inputs-contract: gone] M4: add risk inputs contract (typed schema)
  m4-risk-permission-layer                    c96ba39 [origin/m4-risk-permission-layer: gone] test: fix path guard tests for linux
  m4-risk-state-machine                       cb27384 [origin/m4-risk-state-machine: gone] chore: format risk state machine
  m4-risk-veto-integration                    6fcbdfc [origin/m4-risk-veto-integration: gone] M4: add risk veto integration point + audit event schema
  m4-risk-veto-integration-fix                38ffdae [origin/m4-risk-veto-integration-fix: gone] tests: harden risk gate enforcement and fail-closed behavior
  m4.2-fundamental-permission-integration-wt2 e4b8961 [origin/main: behind 17] M4: Fundamental Risk Permission Layer (#32)
+ m5-hardening-decoupling                     2d7482c (C:/Users/Sepehr/Desktop/buff-core) [origin/m5-hardening-decoupling: gone] Fix selector spec definitions and tests
  m5-strategy-selector                        3f6c5ed [origin/m5-strategy-selector: gone] M5: add 3 engines, 10 strategy profiles, deterministic selector with explainability
  m6-audit-bundle                             9b8a692 [origin/m6-audit-bundle: gone] M6: add deterministic audit bundle exporter
  m6-audit-run                                9c83db6 [origin/m6-audit-run: gone] M6: remove decision_records timestamp patching from audit run
  m6-audit-verify                             2e10708 [origin/m6-audit-verify: gone] M6: add audit bundle verifier
  m6-idempotency-diagnostics                  0cf2d62 [origin/m6-idempotency-diagnostics: gone] fix: avoid dependency on execution.clock in CLI
  m6-idempotency-inflight                     252a4bc [origin/m6-idempotency-inflight: gone] M6: add inflight reservation for idempotency
  m6-idempotency-keying                       898f871 [origin/m6-idempotency-keying: gone] M6: add idempotency keying and dedupe protection
  m6-idempotency-persistence                  c72e522 [origin/m6-idempotency-persistence: gone] M6: add persistent idempotency store (sqlite)
  m6-idempotency-recovery                     527cde4 [origin/m6-idempotency-recovery: gone] M6: add inflight recovery policy
* m6-invariant-guardrails                     dec5b6e [origin/m6-invariant-guardrails: gone] M7: replay/repro + migration + verification report
  m6-order-intent-model                       7969c47 [origin/m6-order-intent-model: gone] M6: add paper order intent model
  main                                        fdaf08e [origin/main: behind 1] M6: End-to-end audit run orchestration (paper run → bundle → verify) (#66)
  pr/m4-risk-gate-hardening                   2e05f90 [origin/pr/m4-risk-gate-hardening: gone] tests: harden safety invariants
  pr/m6-order-intent                          2c55cab [origin/pr/m6-order-intent: gone] fix: remove audit schema dependency from order intent
  wip-extract-docs-only-34                    b4e8c82 [origin/wip-extract-docs-only-34: gone] Docs: extract WIP documentation updates (refs #34)
```

### git diff --name-status origin/main...HEAD
```
M	.gitignore
M	README.md
A	docs/DECISION_RECORD.md
A	docs/REPLAY.md
A	reports/m7_verification_report.md
M	src/audit/__init__.py
A	src/audit/canonical_json.py
A	src/audit/cli_make_snapshot.py
A	src/audit/cli_record_decision.py
M	src/audit/cli_replay.py
A	src/audit/decision_record.py
A	src/audit/make_snapshot.py
A	src/audit/migrate_records.py
A	src/audit/record_decision.py
M	src/audit/replay.py
A	src/audit/self_check.py
A	src/audit/snapshot.py
A	tests/fixtures/decision_payload.json
A	tests/fixtures/legacy_records/legacy_computed_missing_config.json
A	tests/fixtures/legacy_records/legacy_computed_with_snapshot.json
A	tests/fixtures/legacy_records/legacy_fact.json
A	tests/fixtures/snapshot_payload.json
A	tests/test_canonical_json_hardening.py
A	tests/test_cli_replay_m7.py
A	tests/test_config_precedence.py
A	tests/test_decision_record_canonicalization.py
A	tests/test_decision_record_ordering.py
A	tests/test_hashes_ignored_in_core.py
A	tests/test_invariants_no_engine_mutation.py
A	tests/test_migrate_records.py
A	tests/test_replay_determinism.py
A	tests/test_replay_mismatch_diff.py
A	tests/test_replay_missing_config.py
A	tests/test_replay_strictness.py
A	tests/test_self_check.py
A	tests/test_snapshot_roundtrip.py
```

### git diff --stat origin/main...HEAD
```
 .gitignore                                         |   3 +
 README.md                                          |  23 +-
 docs/DECISION_RECORD.md                            | 116 ++++++
 docs/REPLAY.md                                     |  81 +++++
 reports/m7_verification_report.md                  |  93 +++++
 src/audit/__init__.py                              |  23 +-
 src/audit/canonical_json.py                        |  64 +++
 src/audit/cli_make_snapshot.py                     |  26 ++
 src/audit/cli_record_decision.py                   |  30 ++
 src/audit/cli_replay.py                            |  20 +-
 src/audit/decision_record.py                       | 358 +++++++++++++++++++
 src/audit/make_snapshot.py                         |   7 +
 src/audit/migrate_records.py                       | 276 +++++++++++++++
 src/audit/record_decision.py                       |   7 +
 src/audit/replay.py                                | 390 +++++++++++++++++++++
 src/audit/self_check.py                            |  52 +++
 src/audit/snapshot.py                              | 147 +++++++
 tests/fixtures/decision_payload.json               |  38 ++
 .../legacy_computed_missing_config.json            |  30 ++
 .../legacy_computed_with_snapshot.json             |  32 ++
 tests/fixtures/legacy_records/legacy_fact.json     |  16 +
 tests/fixtures/snapshot_payload.json               |  44 +++
 tests/test_canonical_json_hardening.py             |  29 ++
 tests/test_cli_replay_m7.py                        | 122 +++++++
 tests/test_config_precedence.py                    | 145 ++++++++
 tests/test_decision_record_canonicalization.py     |  63 ++++
 tests/test_decision_record_ordering.py             | 145 ++++++++
 tests/test_hashes_ignored_in_core.py               |  46 +++
 tests/test_invariants_no_engine_mutation.py        | 121 +++++++
 tests/test_migrate_records.py                      |  57 +++
 tests/test_replay_determinism.py                   | 114 +++++++
 tests/test_replay_mismatch_diff.py                 |  73 ++++
 tests/test_replay_missing_config.py                | 122 +++++++
 tests/test_replay_strictness.py                    | 176 +++++++++
 tests/test_self_check.py                           |  16 +
 tests/test_snapshot_roundtrip.py                   |  47 +++
 36 files changed, 3126 insertions(+), 26 deletions(-)
```

### ruff check .
```
All checks passed!
```

### pytest -q
```
........................................................................ [ 23%]
........................................................................ [ 46%]
........................................................................ [ 70%]
................................s....................................... [ 93%]
....................                                                     [100%]
============================== warnings summary ===============================
tests/integration/test_run_ingest_offline.py::test_parquet_has_utc_timestamps
  C:\Users\Sepehr\Desktop\Buff\tests\integration\test_run_ingest_offline.py:69: DeprecationWarning: is_datetime64tz_dtype is deprecated and will be removed in a future version. Check `isinstance(dtype, pd.DatetimeTZDtype)` instead.
    assert pd.api.types.is_datetime64tz_dtype(loaded["ts"])

tests/test_audit_verify.py::test_tamper_zip_checksums
  C:\Users\Sepehr\AppData\Local\Programs\Python\Python310\lib\zipfile.py:1506: UserWarning: Duplicate name: 'checksums.txt'
    return self._open_to_write(zinfo, force_zip64=force_zip64)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
307 passed, 1 skipped, 2 warnings in 24.22s
```

## Consistency Checks

- PASS: only one verification report present at reports/m7_verification_report.md
- PASS: diffstat files changed count matches name-status list length (origin/main...HEAD = 36 files)
- PASS: diffstat/name-status refer to the same diff range (origin/main...HEAD)

## Summary
- All checks passed. Report reflects merge-base diff vs origin/main.
