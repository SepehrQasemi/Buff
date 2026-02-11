# Release Precheck (Local)

`release_preflight` is a local-only safety command that syncs `main` with origin using
fast-forward-only pulls, then runs the release gate.

Command:

```bash
python -m tools.release_preflight
```

What it does:
- Verifies the repo is a git work tree and the working tree is clean.
- `git fetch origin`.
- Verifies `main` exists locally or at `origin/main`.
- Switches to `main` (creating it from `origin/main` if needed).
- `git pull --ff-only origin main` (no merges, no rebases).
- Verifies the working tree is still clean.
- Runs `python -m tools.release_gate --strict`.

Reports:
- Writes `reports/release_preflight_report.json` with step-by-step output.

Failure cases (fail-closed):
- Dirty working tree.
- Missing `origin` remote or failed fetch.
- `main` missing locally and at `origin/main`.
- `main` diverged from `origin/main` (fast-forward only pull fails).
- Any release gate failure (ruff, pytest, or MVP smoke).
