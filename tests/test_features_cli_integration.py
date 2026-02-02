from __future__ import annotations

from pathlib import Path

import pandas as pd

from features.build_features import FEATURE_COLUMNS
from features.cli import main
from features.regime import REGIME_COLUMNS
from tests.fixtures.ohlcv_factory import make_ohlcv

FORBIDDEN_TERMS = [
    "signal",
    "side",
    "position",
    "long",
    "short",
    "entry",
    "exit",
    "buy",
    "sell",
    "strategy_id",
]


def test_features_cli_integration(tmp_path: Path) -> None:
    df = make_ohlcv(160)
    input_path = tmp_path / "ohlcv.parquet"
    output_a = tmp_path / "market_state_a.parquet"
    output_b = tmp_path / "market_state_b.parquet"

    df.to_parquet(input_path, index=False)
    assert main(["--input", str(input_path), "--output", str(output_a)]) == 0
    assert main(["--input", str(input_path), "--output", str(output_b)]) == 0

    out_a = pd.read_parquet(output_a)
    out_b = pd.read_parquet(output_b)
    expected = ["timestamp"] + FEATURE_COLUMNS + REGIME_COLUMNS
    assert list(out_a.columns) == expected
    assert list(out_b.columns) == expected
    assert out_a["timestamp"].is_monotonic_increasing
    assert not out_a["timestamp"].duplicated().any()

    lower_cols = [col.lower() for col in out_a.columns]
    for term in FORBIDDEN_TERMS:
        assert all(term not in col for col in lower_cols)

    hash_a = pd.util.hash_pandas_object(out_a, index=False).values.tobytes()
    hash_b = pd.util.hash_pandas_object(out_b, index=False).values.tobytes()
    assert hash_a == hash_b
