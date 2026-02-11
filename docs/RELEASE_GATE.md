# Release Gate (Local)

`tools.release_gate` runs a local release gate with fail-closed behavior and a JSON report.

Command:

```bash
python -m tools.release_gate --strict --timeout-seconds 900
```

## Checks
- `ruff check .`
- `ruff format --check .`
- `pytest -q`
- Optional MVP smoke (`src.tools.mvp_smoke`) when `--with-network-smoke` is enabled

## Flags
- `--strict`: stop at the first failing step (fast-fail).
- `--with-network-smoke`: run the MVP smoke test (requires network access).
- `--timeout-seconds`: per-step timeout for subprocess commands (default: 900).

## Outputs
- Report: `reports/release_gate_report.json`
- High-level fields include:
  - `timestamp_utc`, `finished_at_utc`
  - `strict`, `with_network_smoke`
  - `git_branch`, `git_sha`
  - `python_version`, `ruff_version`, `pytest_version`
  - `steps` (name, status, duration, details)
  - `overall_status`

## Troubleshooting
- Timeout: increase `--timeout-seconds` or investigate the stalled step.
- Ruff/format failures: run `python -m ruff format .` and recheck.
- Pytest failures: run `python -m pytest -q` and fix failing tests.
- Network smoke failures: ensure outbound HTTPS access to `fapi.binance.com` or keep
  `--with-network-smoke` disabled.
