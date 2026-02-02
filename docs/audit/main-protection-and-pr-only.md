# Main branch protection and PR-only policy

## Policy statement
Direct pushes to `main` are prohibited. All changes must be merged via a pull request.

## Required checks (merge gates)
- Required: `ci`
- CodeQL runs on PRs and on `main` (push + schedule) for diagnostics, but is not a required gate because hosted runner capacity can delay PR completion.
- If strict pre-merge CodeQL gating is required, the repo must use self-hosted runners (or guaranteed capacity) so PRs do not deadlock.

## Workflow triggers
- `ci`: pull_request (opened, synchronize, reopened), push to `main`, workflow_dispatch
- `CodeQL`: pull_request (opened, synchronize, reopened), push to `main`, schedule (Mon 06:00 UTC)

## Ruleset / branch protection configuration (main)
- Target branch: `refs/heads/main`
- Require pull request before merging
- Required status checks: `ci` (strict)
- Require review thread resolution
- No force pushes (non-fast-forward)
- No deletions
- Bypass actors: none (applies to admins)

## Implementation status
- Ruleset id: 12378749
- Verification: `gh api /repos/Buff-Trading-AI/Buff/rulesets/12378749`

## Verification checklist
- Read back ruleset and confirm `required_status_checks` includes only `ci`
- Confirm CodeQL workflow runs on PR + `main` but is not required
- Confirm `non_fast_forward` and `deletion` rules present
- Confirm no bypass actors configured
