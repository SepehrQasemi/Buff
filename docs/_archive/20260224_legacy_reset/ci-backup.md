ARCHIVED — NOT AUTHORITATIVE
Superseded by new documentation reset 2026-02-24.
Do not rely on this file for current stage or product direction.

STATUS: DISABLED - self-hosted/Clouding backup CI is not used. Files retained for future re-enable.
Sanity: CI verified on 2026-02-03.
Do not use unless explicitly re-enabled.

# CI Backup (Plan 2)

This repo previously used a two-stage CI strategy (now archived):
1) Normal CI runs on GitHub-hosted runners for every pull request.
2) If the normal CI concludes with **cancelled** or **failure**, a fallback workflow powers on a Clouding VPS, waits for a self-hosted runner, runs the same CI steps, then powers the server off.

## Required runner labels
The self-hosted runner must have these labels:
- `backup`
- `compute`

## Required GitHub Secrets
Create these in the repo settings (no values shown here):
- `CLOUDING_APIKEY`
- `SERVER_ID`

## How to test the fallback
Do not use unless explicitly re-enabled.

## Troubleshooting checklist
- **Runner offline**
  - Ensure the self-hosted runner service is running on the VPS.
  - Confirm the runner has the `backup` label.
- **wait-for-runner timeout**
  - The runner never reported `online` with the `backup` label within 10 minutes.
  - Check the runner logs on the server and verify network access to GitHub.
- **Clouding API 401/403**
  - The API key lacks access or is invalid.
  - Verify `CLOUDING_APIKEY` is correct and has least-privilege access.
- **Archive/unarchive fails**
  - Verify `SERVER_ID` is correct in GitHub Secrets.
  - Check Clouding service status and API availability.
- **Cancelled runs donâ€™t trigger backup**
  - By design, cancelled runs require PR label `use-backup-ci` to avoid wasted server cycles.
  - Failures still trigger backup automatically.

## Security notes
- Never paste API keys or runner tokens into chat or logs.
- Use the least-privilege Clouding API key required to archive/unarchive the server.

## Watchdog and sweep
Archived reference only. Do not use unless explicitly re-enabled.
- `ci-backup-watchdog` (archived) runs after every `ci-backup` completion and always attempts to archive the server.
  - `workflow_run` matches the workflow **name** (`ci-backup`), not the filename.
- `clouding-sweep` (archived) runs on a schedule (every 6 hours) and archives the server if it is not already archived.
  - The sweep skips archiving if a `ci-backup` run is in progress.
  - The sweep queries runs via the workflow file path `ci-backup.yml`; do not rename the file.
- `clouding-archive-now` (archived) can immediately archive the server if it is left running.

## Operator scripts
Archived reference only. Do not use unless explicitly re-enabled.
These scripts help validate Clouding connectivity without touching CI workflows:

Use the archived Clouding operator command strings from the centralized runbook section.
See [Runbook: CI Backup Operations](./05_RUNBOOK_DEV_WORKFLOW.md#ci-backup-operations).

