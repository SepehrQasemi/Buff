# Release Precheck (Deprecated Pointer)

Canonical source:
- [05_RUNBOOK_DEV_WORKFLOW.md](./05_RUNBOOK_DEV_WORKFLOW.md#verification-gates)

Use this command from the runbook:
- `python -m tools.release_preflight --timeout-seconds 900`

Related sections:
- [Before Opening A PR](./05_RUNBOOK_DEV_WORKFLOW.md#before-opening-a-pr)
- [Troubleshooting Matrix](./05_RUNBOOK_DEV_WORKFLOW.md#troubleshooting-matrix)

Why this file is thin:
- PR3 consolidated release verification guidance into one runbook to avoid contradictory command sets.

Historical note:
- Detailed preflight behavior remains in git history and tool help text.
