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
- snapshot_hash: str (SHA256 of canonical JSON with snapshot_hash empty)
  <!-- NOTE (underspecified): Whether digest is computed with snapshot_hash omitted or set to empty string is not specified. -->

The snapshot artifact path is content-addressed as:
`artifacts/snapshots/snapshot_<hash>.json`

<!-- NOTE (underspecified): Format of <hash> (e.g. hex only, with/without "sha256:" prefix) is not specified. -->

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

```
python -m src.audit.record_decision --input tests/fixtures/decision_payload.json --out artifacts/decisions
```

Create a snapshot:

```
python -m src.audit.make_snapshot --input tests/fixtures/snapshot_payload.json --out artifacts/snapshots
```

<!-- NOTE (underspecified): Whether --out is a directory or a full file path is not specified. -->

The command prints the created snapshot path (single line) to stdout.

Replay a decision:

```
python -m src.audit.replay --decision <decision_path.json> --snapshot <snapshot_path.json> --strict
```

Expected outputs:

- `REPLAY_OK strict-core` on success (strict-core).
- `REPLAY_OK non-strict` on success (non-strict).
- `REPLAY_MISMATCH` and a canonical JSON diff list on mismatch, exit code 2.
- `REPLAY_ERROR ...` on missing config or config mismatch, exit code 2.
- Unexpected errors exit with code 1.

Replay records are written to:
`artifacts/replays/replay_<decision_id>.json` unless `--out` is provided.

<!-- NOTE (underspecified): Whether replay --out is a file path or a directory is not specified. -->

Use `--strict-full` to require full payload equality. Use `--json <path>` to write diffs
to a file on mismatch.

When `snapshot.risk_inputs` is present, replay requires at least one of
`inputs.config.risk_config` or `snapshot.config.risk_config`. When both are present, they must
be canonically identical.
