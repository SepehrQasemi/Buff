# Multi-User Isolation Layer (S2)

This document describes the S2 behavior implemented on `main` at commit `7056fb402ad1c13e61c7c2d1294271fc50b128ca`.

## Identity Headers
- Required request header: `X-Buff-User`
- Optional fallback env: `BUFF_DEFAULT_USER`
- If `X-Buff-User` is missing and `BUFF_DEFAULT_USER` is unset, API returns `USER_MISSING`.

## Optional HMAC Mode
- Enabled when `BUFF_USER_HMAC_SECRET` is set.
- Required headers in HMAC mode:
  - `X-Buff-Auth`
  - `X-Buff-Timestamp`
- Canonical string format:
  - `<user_id>\n<method>\n<path>\n<timestamp>`
- Signature:
  - `hex(hmac_sha256(secret, canonical_string))`
- Timestamp window:
  - absolute skew must be `<= 300` seconds.
- Path normalization rules (for canonical string):
  - ignore query and fragment
  - normalize trailing slash (except root `/`)

## Storage Layout
- Per-user run directory:
  - `RUNS_ROOT/users/<user_id>/runs/<run_id>/`
- Per-user registry:
  - `RUNS_ROOT/users/<user_id>/index.json`

## Access Control
- Runs/artifacts/list/read endpoints are user-scoped.
- Cross-user run access returns `404` (`RUN_NOT_FOUND`) to avoid existence leaks.

## Legacy Migration
- If legacy flat runs exist under `RUNS_ROOT/<run_id>` and `BUFF_DEFAULT_USER` is unset:
  - `GET /api/v1/ready` returns `status=degraded` with `LEGACY_MIGRATION_REQUIRED`.
- If `BUFF_DEFAULT_USER` is set:
  - legacy runs migrate into the default user namespace.
  - migrated metadata is marked with `migrated_from_legacy=true`.

## Code References
- `apps/api/security/user_context.py`
- `apps/api/phase6/paths.py`
- `apps/api/phase6/registry.py`
- `apps/api/phase6/run_builder.py`
- `apps/api/main.py`
