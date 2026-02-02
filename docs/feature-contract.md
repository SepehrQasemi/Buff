# Feature Contract

## Purity
- Feature computation is pure: no file I/O, no environment reads, no workspace writes, no global mutation.
- Inputs are in-memory OHLCV snapshots; outputs are in-memory feature frames and manifests.

## Determinism
- Same snapshot + same FeatureSpecs => identical outputs (values, dtypes, column order) and identical manifest.
- Canonicalization uses deterministic JSON (sorted keys, stable float formatting).
- Feature execution order is deterministic and independent of input spec order.

## FeatureSpec schema
Fields:
- feature_id: stable string identifier
- version: int or string (default 1)
- params: JSON-serializable mapping
- lookback: int bars required
- requires: list of input columns required by the feature
- outputs: list of output column names (stable order)
- input_timeframe: optional string (if applicable)

Example:
```
FeatureSpec(
    feature_id="ema_20",
    version=1,
    params={"period": 20},
    lookback=19,
    requires=["close"],
    outputs=["ema_20"],
)
```

## Canonicalization + ordering
- Params are serialized to canonical JSON bytes using `audit.canonical_json`.
- Specs are sorted by:
  1) feature_id
  2) canonical_params_json_bytes
  3) version (string)
- Output columns are grouped by spec order, then by spec.outputs order.
- Manifest entries follow the same sorted spec order.

## Feature manifest (schema_version=1)
Each manifest entry contains:
- schema_version: 1
- feature_id
- version
- params_canonical_json
- lookback
- requires
- outputs
- input_timeframe (only when set)

## Error semantics (deterministic codes)
- feature_input_invalid: OHLCV contract failure (timestamp, types, monotonicity)
- feature_missing_required_columns: missing required OHLCV base columns or per-spec requires
- feature_unknown_id: feature_id not in registry
- feature_params_invalid: params include unknown keys or non-serializable values
- feature_spec_invalid: spec object is not a FeatureSpec
- feature_output_mismatch: outputs length does not match computed columns
- feature_output_type_invalid: unsupported output type
- feature_output_conflict: duplicate output column name across specs
- insufficient_lookback: input length < spec.lookback
