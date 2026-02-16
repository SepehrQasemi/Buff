# Release Gate (Deprecated Pointer)

Canonical source:
- [05_RUNBOOK_DEV_WORKFLOW.md](./05_RUNBOOK_DEV_WORKFLOW.md#verification-gates)

Use this command from the runbook:
- `python -m tools.release_gate --strict --timeout-seconds 900`

Related sections:
- [Before Opening A PR](./05_RUNBOOK_DEV_WORKFLOW.md#before-opening-a-pr)
- [Troubleshooting Matrix](./05_RUNBOOK_DEV_WORKFLOW.md#troubleshooting-matrix)

Why this file is thin:
- PR3 moved release-gate execution and recovery guidance to a single runbook source.

Historical note:
- Prior details on checks/flags/outputs are preserved in git history and command help output.
