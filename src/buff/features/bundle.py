"""Feature bundle computation, validation, and persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from buff.data.contracts import REQUIRED_COLUMNS, validate_ohlcv
from buff.features.canonical import canonical_json_bytes
from buff.features.contract import FeatureSpec, sort_specs
from buff.features.metadata import write_json
from buff.features.runner_pure import run_features_pure


FEATURE_BUNDLE_SCHEMA_VERSION = 1
FEATURE_BUNDLE_PARQUET_NAME = "market_state.parquet"

PARQUET_COMPRESSION = "zstd"
PARQUET_COMPRESSION_LEVEL = 3
PARQUET_ROW_GROUP_SIZE = 100_000
PARQUET_DATA_PAGE_SIZE = 1_048_576
PARQUET_WRITE_STATISTICS = False


class FeatureBundleError(ValueError):
    """Base error for feature bundle failures."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class FeatureBundleValidationError(FeatureBundleError):
    """Raised when a feature bundle fails validation."""


@dataclass(frozen=True)
class FeatureTimeBounds:
    start_utc: str | None
    end_utc: str | None
    start_inclusive: bool
    end_inclusive: bool
    as_of_utc: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_utc": self.start_utc,
            "end_utc": self.end_utc,
            "start_inclusive": self.start_inclusive,
            "end_inclusive": self.end_inclusive,
            "as_of_utc": self.as_of_utc,
        }


@dataclass(frozen=True)
class FeatureBundleMetadata:
    schema_version: int
    run_id: str
    created_at_utc: str
    source_fingerprint: str
    source_schema: Mapping[str, str]
    source_paths: Sequence[str]
    time_bounds: FeatureTimeBounds
    specs: Sequence[FeatureSpec]
    dependency_graph: Mapping[str, Sequence[str]]
    code_fingerprint: str
    bundle_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "created_at_utc": self.created_at_utc,
            "source_fingerprint": self.source_fingerprint,
            "source_schema": dict(self.source_schema),
            "source_paths": list(self.source_paths),
            "time_bounds": self.time_bounds.to_dict(),
            "features": [spec.to_dict() for spec in self.specs],
            "dependency_graph": {
                key: list(values) for key, values in self.dependency_graph.items()
            },
            "code_fingerprint": self.code_fingerprint,
            "bundle_fingerprint": self.bundle_fingerprint,
        }


def _iso_utc(value: pd.Timestamp | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        ts = value.to_pydatetime()
    else:
        ts = value
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts = ts.astimezone(timezone.utc)
    return ts.isoformat().replace("+00:00", "Z")


def _fingerprint_frame(df: pd.DataFrame) -> str:
    if df.empty:
        schema = "|".join(f"{col}:{df[col].dtype}" for col in df.columns)
        return sha256(schema.encode("utf-8")).hexdigest()
    hashed = pd.util.hash_pandas_object(df, index=True).values.tobytes()
    schema = "|".join(f"{col}:{df[col].dtype}" for col in df.columns)
    payload = hashed + schema.encode("utf-8")
    return sha256(payload).hexdigest()


def _spec_id(spec: FeatureSpec) -> str:
    return f"{spec.feature_id}@{spec.version}"


def _dependency_graph_ids(specs: Sequence[FeatureSpec]) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = {}
    for spec in specs:
        deps = [f"{dep.name}@{dep.version}" for dep in spec.dependencies]
        graph[_spec_id(spec)] = sorted(deps)
    return graph


def _bundle_fingerprint(payload: Mapping[str, Any]) -> str:
    return sha256(canonical_json_bytes(payload)).hexdigest()


def compute_features(
    df_ohlcv_1m: pd.DataFrame,
    specs: Sequence[FeatureSpec],
) -> tuple[pd.DataFrame, FeatureBundleMetadata]:
    if not isinstance(df_ohlcv_1m, pd.DataFrame):
        raise FeatureBundleValidationError("feature_input_invalid")

    if not all(col in df_ohlcv_1m.columns for col in REQUIRED_COLUMNS):
        raise FeatureBundleValidationError("feature_missing_required_columns")

    try:
        input_df = validate_ohlcv(df_ohlcv_1m)
    except ValueError as exc:
        raise FeatureBundleValidationError("feature_input_invalid") from exc
    if input_df.empty:
        start_utc = None
        end_utc = None
    else:
        start_utc = _iso_utc(input_df.index[0])
        end_utc = _iso_utc(input_df.index[-1])

    ordered_specs = sort_specs(specs)
    features_df, _ = run_features_pure(df_ohlcv_1m, ordered_specs, validate_contract=True)

    if features_df.empty:
        timestamp_col = pd.Series([], dtype="datetime64[ns, UTC]", name="timestamp")
    else:
        timestamp_col = pd.Series(features_df.index, index=features_df.index, name="timestamp")

    features_out = features_df.copy()
    features_out.insert(0, "timestamp", timestamp_col)

    source_fingerprint = str(
        df_ohlcv_1m.attrs.get("source_fingerprint") or _fingerprint_frame(input_df)
    )
    source_schema = {col: str(df_ohlcv_1m[col].dtype) for col in df_ohlcv_1m.columns}
    source_paths = sorted(list(df_ohlcv_1m.attrs.get("source_paths", [])))

    as_of_utc = str(df_ohlcv_1m.attrs.get("as_of_utc") or end_utc or "1970-01-01T00:00:00Z")
    created_at_utc = str(df_ohlcv_1m.attrs.get("created_at_utc") or as_of_utc)
    run_id = str(df_ohlcv_1m.attrs.get("run_id") or f"run-{source_fingerprint[:12]}")
    code_fingerprint = str(df_ohlcv_1m.attrs.get("code_fingerprint") or "unknown")

    time_bounds = FeatureTimeBounds(
        start_utc=start_utc,
        end_utc=end_utc,
        start_inclusive=True,
        end_inclusive=True,
        as_of_utc=as_of_utc,
    )

    graph = _dependency_graph_ids(ordered_specs)
    fingerprint_payload = {
        "schema_version": FEATURE_BUNDLE_SCHEMA_VERSION,
        "source_fingerprint": source_fingerprint,
        "time_bounds": time_bounds.to_dict(),
        "features": [spec.to_dict() for spec in ordered_specs],
        "code_fingerprint": code_fingerprint,
    }
    bundle_fingerprint = _bundle_fingerprint(fingerprint_payload)

    metadata = FeatureBundleMetadata(
        schema_version=FEATURE_BUNDLE_SCHEMA_VERSION,
        run_id=run_id,
        created_at_utc=created_at_utc,
        source_fingerprint=source_fingerprint,
        source_schema=source_schema,
        source_paths=source_paths,
        time_bounds=time_bounds,
        specs=ordered_specs,
        dependency_graph=graph,
        code_fingerprint=code_fingerprint,
        bundle_fingerprint=bundle_fingerprint,
    )
    return features_out, metadata


def _prepare_feature_frame(
    df: pd.DataFrame,
    specs: Sequence[FeatureSpec],
) -> pd.DataFrame:
    if "timestamp" not in df.columns:
        raise FeatureBundleValidationError("feature_missing_timestamp")

    ordered_specs = sort_specs(specs)
    expected_columns = ["timestamp"] + [col for spec in ordered_specs for col in spec.outputs]
    missing = [col for col in expected_columns if col not in df.columns]
    if missing:
        raise FeatureBundleValidationError("feature_output_missing")

    ordered = df[expected_columns].copy()
    ordered["timestamp"] = pd.to_datetime(ordered["timestamp"], utc=True, errors="coerce")
    if ordered["timestamp"].isna().any():
        raise FeatureBundleValidationError("feature_timestamp_invalid")
    ordered = ordered.reset_index(drop=True)
    ordered = ordered.sort_values("timestamp").reset_index(drop=True)

    for spec in ordered_specs:
        for col in spec.outputs:
            dtype = spec.output_dtypes.get(col, "float64")
            ordered[col] = pd.to_numeric(ordered[col], errors="coerce").astype(dtype)
    return ordered


def validate_feature_bundle(
    df_features: pd.DataFrame,
    metadata: FeatureBundleMetadata | Mapping[str, Any],
) -> None:
    meta_dict = (
        metadata.to_dict() if isinstance(metadata, FeatureBundleMetadata) else dict(metadata)
    )
    if meta_dict.get("schema_version") != FEATURE_BUNDLE_SCHEMA_VERSION:
        raise FeatureBundleValidationError("feature_bundle_schema_invalid")

    specs_payload = meta_dict.get("features")
    if not isinstance(specs_payload, list) or not specs_payload:
        raise FeatureBundleValidationError("feature_specs_missing")

    if "timestamp" not in df_features.columns:
        raise FeatureBundleValidationError("feature_missing_timestamp")

    ts = pd.to_datetime(df_features["timestamp"], utc=True, errors="coerce")
    if ts.isna().any():
        raise FeatureBundleValidationError("feature_timestamp_invalid")
    if ts.duplicated().any():
        raise FeatureBundleValidationError("feature_timestamp_duplicate")
    if not ts.is_monotonic_increasing:
        raise FeatureBundleValidationError("feature_timestamp_not_monotonic")

    spec_ids = set()
    for spec in specs_payload:
        if not isinstance(spec, Mapping):
            raise FeatureBundleValidationError("feature_spec_invalid")
        feature_id = spec.get("feature_id")
        version = spec.get("version")
        if not isinstance(feature_id, str) or not feature_id:
            raise FeatureBundleValidationError("feature_spec_invalid")
        if not isinstance(version, (int, str)) or isinstance(version, bool):
            raise FeatureBundleValidationError("feature_spec_invalid")
        spec_ids.add(f"{feature_id}@{version}")

    dep_graph = meta_dict.get("dependency_graph", {})
    if not isinstance(dep_graph, Mapping):
        raise FeatureBundleValidationError("feature_dependency_graph_invalid")
    for key, deps in dep_graph.items():
        if key not in spec_ids:
            raise FeatureBundleValidationError("feature_dependency_graph_invalid")
        if not isinstance(deps, list):
            raise FeatureBundleValidationError("feature_dependency_graph_invalid")
        for dep in deps:
            if dep not in spec_ids:
                raise FeatureBundleValidationError("feature_dependency_missing")

    for spec in specs_payload:
        outputs = spec.get("outputs", [])
        lookback = spec.get("lookback", 0)
        output_dtypes = spec.get("output_dtypes", {})
        if not isinstance(outputs, list):
            raise FeatureBundleValidationError("feature_spec_invalid")
        if not isinstance(lookback, int) or lookback < 0:
            raise FeatureBundleValidationError("feature_spec_invalid")
        if output_dtypes and not isinstance(output_dtypes, Mapping):
            raise FeatureBundleValidationError("feature_output_dtype_invalid")
        for col in outputs:
            if col not in df_features.columns:
                raise FeatureBundleValidationError("feature_output_missing")
            if isinstance(output_dtypes, Mapping) and col in output_dtypes:
                expected = str(output_dtypes[col])
                actual = str(df_features[col].dtype)
                if expected and actual != expected:
                    raise FeatureBundleValidationError("feature_output_dtype_invalid")
            if lookback == 0:
                continue
            series = pd.to_numeric(df_features[col], errors="coerce")
            if series.iloc[lookback:].isna().any():
                raise FeatureBundleValidationError("feature_output_nan")


def write_feature_bundle(
    out_dir: str | Path,
    df_features: pd.DataFrame,
    metadata: FeatureBundleMetadata,
) -> tuple[Path, Path]:
    validate_feature_bundle(df_features, metadata)

    out_path = Path(out_dir)
    if out_path.suffix.lower() == ".parquet":
        parquet_path = out_path
    else:
        parquet_path = out_path / "features" / FEATURE_BUNDLE_PARQUET_NAME
    meta_path = parquet_path.with_suffix(".meta.json")

    ordered = _prepare_feature_frame(df_features, metadata.specs)
    table = pa.Table.from_pandas(ordered, preserve_index=False)
    table = table.replace_schema_metadata(None)

    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        table,
        parquet_path,
        compression=PARQUET_COMPRESSION,
        compression_level=PARQUET_COMPRESSION_LEVEL,
        use_dictionary=False,
        row_group_size=PARQUET_ROW_GROUP_SIZE,
        data_page_size=PARQUET_DATA_PAGE_SIZE,
        write_statistics=PARQUET_WRITE_STATISTICS,
    )

    write_json(meta_path, metadata.to_dict())
    return parquet_path, meta_path
