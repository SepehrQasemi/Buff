# CI Backup (Plan 2)

This repo uses a two-stage CI strategy:
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
1) Open a PR to trigger the normal `ci` workflow.
2) Cancel the running `ci` job from the Actions UI.
3) If you want the fallback on a cancelled run, add the PR label `use-backup-ci`.
4) Confirm `ci-backup` starts, powers on the server, waits for the runner, runs tests, and powers off the server.

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
- **Cancelled runs don’t trigger backup**
  - By design, cancelled runs require PR label `use-backup-ci` to avoid wasted server cycles.
  - Failures still trigger backup automatically.

## Security notes
- Never paste API keys or runner tokens into chat or logs.
- Use the least-privilege Clouding API key required to archive/unarchive the server.

## Operator scripts
These scripts help validate Clouding connectivity without touching CI workflows:

```bash
export CLOUDING_APIKEY="..."
./scripts/clouding_list_servers.sh
```

```bash
export CLOUDING_APIKEY="..."
export SERVER_ID="..."
./scripts/clouding_power.sh unarchive
./scripts/clouding_power.sh archive
```
