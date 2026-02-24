ARCHIVED — NOT AUTHORITATIVE
Superseded by new documentation reset 2026-02-24.
Do not rely on this file for current stage or product direction.

# Decision Record (M7)

This document defines the deterministic Decision Record schema used for replay and reproducibility.

## Schema (required fields)

Top-level:
- decision_id: str (stable, deterministic identifier)
- ts_utc: str (ISO-8601 with timezone, e.g. `2026-02-01T00:00:00Z`)
- symbol: str
- timeframe: str
- code_version:
  - git_commit: str
  - dirty: bool
- run_context:
  - seed: int
  - python: str
  - platform: str
- artifacts:
  - snapshot_ref: str | null
  - features_ref: str | null
- inputs:
  - market_features: dict
  - risk_state: str
  - selector_inputs: dict
  - config: dict
  - risk_mode: "fact" | "computed"
- selection:
  - selected: bool
  - strategy_id: str | null
  - status: "selected" | "no_selection" | "blocked"
  - score: float | int | null
  - reasons: list[str]
  - rules_fired: list[str]
- outcome:
  - decision: str
  - allowed: bool
  - notes: str | null
- hashes:
  - core_hash: str
  - content_hash: str
  - inputs_hash: str | null

## Schema Versioning & Compatibility

Version format: `MAJOR.MINOR.PATCH` (example: `1.0.0`).

Versioning rules:
- MAJOR: breaking changes (field removals, semantic changes, or incompatible types).
- MINOR: backward-compatible additive changes (new optional fields, new enum values).
- PATCH: clarifications or fixes that do not change schema shape.

Compatibility rules:
- Readers must ignore unknown fields.
- Required fields must exist and keep their meaning for a given MAJOR version.
- Writers must emit all required fields for the declared schema version.
- MINOR additions must be optional and safe to ignore by older readers.

Migration expectations:
- Any MAJOR bump must provide a documented migration map and tooling (if automated).
- Records should be migrated before strict replay/verification when a MAJOR changes.

## Canonical JSON rules

All decision record JSON must be serialized using the canonical encoder in `src/audit/canonical_json.py`:

- UTF-8 encoding.
- Sorted keys for all dicts.
- No whitespace outside string literals.
- Stable float formatting: floats quantized to 8 dp (ROUND_HALF_UP), fixed-point; ints remain integers.
- Non-finite floats/decimals (NaN/Infinity) are rejected with a ValueError that includes the JSON path.
- Lists preserve order (no re-sorting).

## Hashing rules

- `inputs_hash` = SHA256 of canonical JSON bytes of the `inputs` section.
- `core_hash` = SHA256 of the canonical JSON bytes of the core payload object (the subset
  object: decision_id, symbol, timeframe, artifacts.snapshot_ref, artifacts.features_ref,
  inputs, selection, outcome).
- `content_hash` = SHA256 of canonical JSON bytes of the full payload:
  - decision_id, ts_utc, symbol, timeframe
  - code_version (including dirty)
  - run_context (including python/platform)
  - artifacts, inputs, selection, outcome
- Hashes are computed over payloads that exclude the `hashes` section entirely.

This avoids self-referential hashing and ensures stable digests.

## Example

```json
{"artifacts":{"features_ref":null,"snapshot_ref":"snapshot_93c1...json"},"code_version":{"dirty":false,"git_commit":"deadbeef"},"decision_id":"dec-001","hashes":{"content_hash":"sha256:...","core_hash":"sha256:...","inputs_hash":"sha256:..."},"inputs":{"config":{"risk_config":{"missing_red":0.2}},"market_features":{"trend_state":"up","volatility_regime":"low"},"risk_mode":"computed","risk_state":"GREEN","selector_inputs":{"selector_version":1}},"outcome":{"allowed":true,"decision":"SELECT","notes":null},"run_context":{"platform":"linux","python":"3.11.9","seed":42},"selection":{"reasons":["trend+breakout & vol not high"],"rules_fired":["R2"],"score":1.23456789,"selected":true,"status":"selected","strategy_id":"TREND_FOLLOW"},"symbol":"BTCUSDT","timeframe":"1m","ts_utc":"2026-02-01T00:00:00Z"}
```

Notes:
- Use `selection.selected=false`, `selection.strategy_id=null`, and `selection.status="no_selection"`
  when no strategy is selected.
- For decision records, `reasons` and `rules_fired` must be sorted lexicographically by the
  producer before canonical serialization; the canonical encoder does not re-sort lists.
- If risk evaluation is replayed from `snapshot.risk_inputs`, the corresponding
  `inputs.config.risk_config` must be present and is included in the core hash.
- In this document, "snapshot" refers to the snapshot artifact used as replay input.

## Corruption Handling

- Report generation (`src.reports.decision_report`) fails closed on invalid JSON lines and
  raises `invalid_json_line:<line_no>` for corrupted or truncated JSONL records.
- Replay loading (`src.audit.replay.load_decision_records`) skips invalid lines and tracks
  an error count; any non-zero error count should be treated as data corruption.
- If corruption is detected, regenerate artifacts from source inputs or discard the run.

## Risk replay semantics

- `risk_mode="fact"`: `inputs.risk_state` is treated as an input fact and replay does not
  recompute risk. `risk_config` is optional unless snapshot risk inputs are present.
- `risk_mode="computed"`: replay recomputes risk from `snapshot.risk_inputs` and
  `risk_config`. If `snapshot.risk_inputs` is missing, replay fails closed.

## Migration (v1 -> v2 structural mapping)

Do not infer business logic. Only map fields structurally:

| Legacy field | New field(s) |
| --- | --- |
| `selection.strategy_id` is missing or null | `selection.selected=false`, `selection.status="no_selection"`, `selection.strategy_id=null` |
| `selection.strategy_id` is empty string AND `strategy.name` + `strategy.version` exist | `selection.strategy_id="{name}@{version}"`, `selection.selected=true`, `selection.status="selected"` |
| `selection.strategy_id` is empty string AND `strategy` fields are missing | Migration fails (fail-closed) with a clear error. |
| `selection.strategy_id` is present | `selection.selected=true`, `selection.status="selected"`, `selection.strategy_id=<old>` |
| Explicit blocked indicator (e.g., `outcome.allowed=false` AND `outcome.decision=="blocked"`) | `selection.status="blocked"` (only if explicitly indicated) |

If the legacy record contains no explicit blocked indicator, do not set `status="blocked"`.

Empty string strategy_id is not valid without a strategy reference.

### CLI migration helper

Use the centralized migration helper command from the runbook when converting legacy records.
See [Runbook: Decision Record Migration Helper](./05_RUNBOOK_DEV_WORKFLOW.md#decision-record-migration-helper).

Migration rules (structural only):
- Add `selection.selected` + `selection.status` based on presence of `selection.strategy_id`.
- Add `inputs.risk_mode` ("computed" if snapshot risk_inputs exist, else "fact").
- Recompute hashes per the hashing rules in this document.
