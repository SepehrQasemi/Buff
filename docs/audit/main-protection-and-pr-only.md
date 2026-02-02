# Main branch protection and PR-only policy

## Policy statement
Direct pushes to `main` are prohibited. All changes must be made through a pull request.

## Required checks
The following required status checks must pass before merging to `main`:
- `ci`

## Required review policy
- At least 1 approving review is required before merge.
- Administrators are not exempt.

## What happened
On Feb 2, 2026, commit `cc01ee6` was pushed directly to `main`, bypassing PR review and required checks. The CI workflow then failed on the main branch.

## Corrective actions
- Implemented/updated CI so the `ci` workflow runs `ruff format --check`, `ruff check`, and `pytest -q` and passes.
- Added an explicit PR checklist to reinforce "no direct push to main" and local gate expectations.
- Enforced branch protection (ruleset or branch protection) to require PRs, required checks, and at least one approval; force pushes and deletions are blocked.

## Ruleset / branch protection configuration
- Target branch: `main`
- Require pull request before merging
- Require at least 1 approval
- Require status checks: `ci`
- Require branches to be up to date before merging
- Restrict direct pushes
- Include administrators
- Block force pushes and deletions

## Implementation status
- Ruleset applied via API on Feb 2, 2026 (ruleset id: 12378749)
- Verification: `gh api /repos/Buff-Trading-AI/Buff/rulesets`

## Verification checklist
- Read back rulesets: `gh api /repos/Buff-Trading-AI/Buff/rulesets`
- Confirm ruleset targeting `refs/heads/main` is `active`
- Confirm rules include:
  - `pull_request` with `required_approving_review_count: 1`
  - `required_status_checks` with `context: "ci"` and `strict_required_status_checks_policy: true`
  - `non_fast_forward` and `deletion`
- Required check name: `ci`
