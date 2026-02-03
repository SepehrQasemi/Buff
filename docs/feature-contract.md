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
- description: human-readable description
- params: JSON-serializable mapping
- lookback: int bars required
- lookback_timedelta: optional string duration (e.g., \"5m\")
- requires: list of input columns required by the feature
- dependencies: list of feature dependencies (name + version)
- outputs: list of output column names (stable order)
- output_dtypes: mapping of output column -> dtype
- input_timeframe: string (default \"1m\")

Example:
```
FeatureSpec(
    feature_id="ema_20",
    version=1,
    description="ema_20 feature",
    params={"period": 20},
    lookback=19,
    requires=["close"],
    outputs=["ema_20"],
    output_dtypes={"ema_20": "float64"},
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

## Feature manifest (schema_version=2)
Each manifest entry contains:
- schema_version: 2
- feature_id
- version
- description
- params_canonical_json
- lookback
- lookback_timedelta
- requires
- dependencies
- outputs
- output_dtypes
- input_timeframe (only when set)

## Feature bundle metadata (schema_version=1)
Generated artifacts include deterministic metadata:
- schema_version
- run_id / created_at_utc
- source_fingerprint + source_schema + source_paths
- time_bounds: start/end inclusive + as_of_utc
- features: fully resolved FeatureSpec list
- dependency_graph (feature_id@version -> dependencies)
- code_fingerprint
- bundle_fingerprint
- Stored next to the parquet as `market_state.meta.json`.

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
