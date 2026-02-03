from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from buff.features.bundle import PARQUET_COMPRESSION, compute_features, write_feature_bundle
from buff.features.contract import build_feature_specs_from_registry, sort_specs
from buff.features.registry import FEATURES
from tests.fixtures.ohlcv_factory import make_ohlcv


def test_feature_bundle_parquet_ordering_and_compression(tmp_path: Path) -> None:
    df = make_ohlcv(240)
    specs = build_feature_specs_from_registry(FEATURES)
    features_df, metadata = compute_features(df, specs)

    parquet_path, _ = write_feature_bundle(tmp_path, features_df, metadata)
    out = pd.read_parquet(parquet_path, engine="pyarrow")

    ordered_specs = sort_specs(specs)
    expected_columns = ["timestamp"] + [col for spec in ordered_specs for col in spec.outputs]
    assert list(out.columns) == expected_columns
    assert out["timestamp"].is_monotonic_increasing
    assert not out["timestamp"].duplicated().any()

    parquet_meta = pq.ParquetFile(parquet_path).metadata
    assert parquet_meta.num_row_groups == 1
    row_group = parquet_meta.row_group(0)
    for idx in range(row_group.num_columns):
        column = row_group.column(idx)
        assert str(column.compression).upper() == PARQUET_COMPRESSION.upper()
        assert "RLE_DICTIONARY" not in column.encodings
