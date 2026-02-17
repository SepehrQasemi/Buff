# PROJECT_STATE

## Authoritative Notice

This file is the single source of truth for:
- Current project stage
- Current objective
- Definition of Done
- Active constraints
- Next transition gate

No other document determines current stage.

---

## Machine-Readable Snapshot
CURRENT_STAGE=S0_DETERMINISTIC_ANALYSIS_ONLY_ENGINE
LAST_MERGED_PR=#195 https://github.com/Buff-Trading-AI/Buff/pull/195
LAST_MERGED_SHA=ffefbfd54014973276b1eefe4c1132694d705018

NEXT_3_ACTIONS:
1) Merge PR #196 after green checks and update this snapshot to that merge commit.
2) Keep docs PRs in Lane 1 (docs/** and README.md only).
3) Keep tooling changes in Lane 2 (scripts/**) and never mix them into docs-only PRs.

HOW_TO_REFRESH:
gh pr list --state open --limit 50
gh pr view <number> --json number,url,state,mergedAt,mergeCommit,headRefName,baseRefName
gh pr checks <number>
git log -1 --oneline

---

## Current Stage
S0 - Deterministic Analysis-Only Engine

## Stage Description
Fail-closed, artifact-driven, deterministic analysis system.
No trade execution.
No broker integration.
No live state mutation.

## Current Objective
Harden documentation boundaries and enforce contract authority.

## Definition of Done
- All normative constraints centralized
- No broken links
- Single-source operational command strings
- CI green
- release_gate PASS

## Active Constraints
- Execution is out of scope
- Broker APIs forbidden
- Deterministic runtime only
- Fail-closed error handling
- Canonical contract authority enforced

## Next Stage Candidate
S1 - Observability And Run Intelligence Layer

## Transition Gate Requirements (S0 -> S1)
- Run indexing layer
- Queryable artifact registry
- Structured runtime metrics
- Observability documentation
- Updated PROJECT_STATE.md

## Workflow Lanes
- Lane 1 (DocsOnly): `docs/**` and `README.md` only.
- Lane 2 (Tooling): `scripts/**` and automation support files.

## Solo Mode
- Local guardrails are warn-only to avoid blocking solo development loops.
- PR gate enforcement is strict and authoritative.
- Untracked `scripts/**` files are allowed while developing locally.
- Before merging a DocsOnly PR, any `scripts/**` local work must be:
  - committed in a Tooling lane branch/PR, or
  - removed from local workspace.

## Last Verified Commit
PR #195 - docs hardening and normalization
