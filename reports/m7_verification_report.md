# M7 Verification Report

Branch: m6-invariant-guardrails
Commit: 89b106e62e015874e9e1028638ed4c911fad4a1d
Date: 2026-02-01

## Command Outputs

### git status -sb
```
## m6-invariant-guardrails...origin/m6-invariant-guardrails
M  .gitignore
M  README.md
A  docs/DECISION_RECORD.md
A  docs/REPLAY.md
A  reports/m7_verification_report.md
M  src/audit/__init__.py
A  src/audit/canonical_json.py
A  src/audit/cli_make_snapshot.py
A  src/audit/cli_record_decision.py
M  src/audit/cli_replay.py
A  src/audit/decision_record.py
A  src/audit/make_snapshot.py
A  src/audit/migrate_records.py
A  src/audit/record_decision.py
M  src/audit/replay.py
A  src/audit/self_check.py
A  src/audit/snapshot.py
A  tests/fixtures/decision_payload.json
A  tests/fixtures/legacy_records/legacy_computed_missing_config.json
A  tests/fixtures/legacy_records/legacy_computed_with_snapshot.json
A  tests/fixtures/legacy_records/legacy_fact.json
A  tests/fixtures/snapshot_payload.json
A  tests/test_canonical_json_hardening.py
A  tests/test_cli_replay_m7.py
A  tests/test_config_precedence.py
A  tests/test_decision_record_canonicalization.py
A  tests/test_decision_record_ordering.py
A  tests/test_hashes_ignored_in_core.py
A  tests/test_migrate_records.py
A  tests/test_replay_determinism.py
A  tests/test_replay_mismatch_diff.py
A  tests/test_replay_missing_config.py
A  tests/test_replay_strictness.py
A  tests/test_self_check.py
A  tests/test_snapshot_roundtrip.py
```

### git diff --name-status origin/main..HEAD
```
A	tests/test_invariants_no_engine_mutation.py
```

### git diff --stat origin/main..HEAD
```
 tests/test_invariants_no_engine_mutation.py | 121 ++++++++++++++++++++++++++++
 1 file changed, 121 insertions(+)
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
307 passed, 1 skipped, 2 warnings in 25.04s
```

## Consistency Checks

- PASS: diffstat files changed count matches name-status list length (origin/main..HEAD = 1 file)
- PASS: diffstat/name-status refer to the same diff range (origin/main..HEAD)
- PASS: only one verification report present at reports/m7_verification_report.md
- PASS: README.md links to reports/m7_verification_report.md

## Summary
- All checks passed. No doc/CLI mismatches detected.
