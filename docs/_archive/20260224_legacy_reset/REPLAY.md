ARCHIVED — NOT AUTHORITATIVE
Superseded by new documentation reset 2026-02-24.
Do not rely on this file for current stage or product direction.

# Replay & Reproducibility (M7)

This document describes the snapshot format, replay runner, and CLI usage.

## Snapshot format

Snapshots capture the minimal inputs required to replay a decision:

- snapshot_version: int
- decision_id: str
- symbol: str
- timeframe: str
- market_data: list[dict] | null (optional OHLCV window)
- features: dict | null (optional precomputed features)
- risk_inputs: dict | null (inputs used by risk evaluation)
- config: dict | null (includes risk_config used to evaluate risk_inputs)
- selector_inputs: dict | null (inputs used by selector)
- snapshot_hash: str (SHA256 of canonical JSON with snapshot_hash omitted)

The snapshot artifact path is content-addressed as:
`artifacts/snapshots/snapshot_<hash>.json`

Hash format: lowercase hex, no prefix.

Canonical JSON rules are implemented in `src/audit/canonical_json.py` (UTF-8, sorted keys, no whitespace).

## Replay equivalence

By default, replay compares the core payloads of the original and replayed record:

- decision_id, symbol, timeframe
- artifacts.snapshot_ref, artifacts.features_ref
- inputs (including config)
- selection
- outcome

Non-strict mode ignores stored hashes and compares the core payload directly.

With `--strict`, replay requires the core payloads to match (strict-core).
With `--strict-full`, replay requires full payloads (including metadata) to match.

Mode | Compares | Requires config? | Requires same environment? | Purpose
non-strict | core canonical bytes | depends on risk_mode | no | regression / drift detection
strict-core | core canonical bytes | depends on risk_mode | no | CI reproducibility gate
strict-full | full canonical bytes (metadata preserved) | depends on risk_mode | yes | forensic identical replay

## CLI usage

Record a decision payload (canonical JSON + hashes):
Use the centralized record command in the runbook.
See [Runbook: Record Decision Payload](./05_RUNBOOK_DEV_WORKFLOW.md#record-decision-payload).

Create a snapshot:
Use the centralized snapshot command in the runbook.
See [Runbook: Create Snapshot](./05_RUNBOOK_DEV_WORKFLOW.md#create-snapshot).

`--out` is a directory; the snapshot file is written inside it.

The command prints the created snapshot path (single line) to stdout.

Replay a decision:
Use the centralized replay command in the runbook.
See [Runbook: Replay Decision](./05_RUNBOOK_DEV_WORKFLOW.md#replay-decision).

Expected outputs:

- `REPLAY_OK strict-core` on success (strict-core).
- `REPLAY_OK non-strict` on success (non-strict).
- `REPLAY_MISMATCH` and a canonical JSON diff list on mismatch, exit code 2.
- `REPLAY_ERROR ...` on missing config or config mismatch, exit code 2.
- Unexpected errors exit with code 1.

Replay records are written to:
`artifacts/replays/replay_<decision_id>.json` unless `--out` is provided.

`--out` is a directory; the replay file is written inside it. Passing a file path is an error.

Use `--strict-full` to require full payload equality. Use `--json <path>` to write diffs
to a file on mismatch.

When `snapshot.risk_inputs` is present, replay requires at least one of
`inputs.config.risk_config` or `snapshot.config.risk_config`. When both are present, they must
be canonically identical.
