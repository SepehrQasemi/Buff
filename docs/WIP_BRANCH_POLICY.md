# WIP Branch Policy

WIP backup branches (for example, `wip-local-dirty-backup`) preserve unscoped edits.
These branches are **NOT** PR-ready and must **NOT** be merged directly.

## Do-Not-Merge Rule
- **DO NOT MERGE** any branch whose name starts with `wip-` or contains `wip`/`dirty-backup`.
- Always create a clean branch from `main` and port only a single, scoped change per PR.
- Keep WIP branches as archival references until all useful changes are extracted or discarded.

## Reviewer Checklist
- Block any PR that targets `main` from a WIP branch.
- Require a clean branch with a single concern before review.
