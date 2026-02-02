from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from features.build_features import build_features
from features.regime import build_market_state, write_market_state
from tests.fixtures.ohlcv_factory import make_ohlcv


def _hash_frame(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    digest.update(pd.util.hash_pandas_object(frame, index=True).values.tobytes())
    return digest.hexdigest()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_features_reproducible(tmp_path: Path) -> None:
    df = make_ohlcv(240)
    out_a = build_market_state(build_features(df))
    out_b = build_market_state(build_features(df))
    assert _hash_frame(out_a) == _hash_frame(out_b)

    path_a = write_market_state(out_a, tmp_path / "a.parquet")
    path_b = write_market_state(out_b, tmp_path / "b.parquet")
    assert _hash_file(path_a) == _hash_file(path_b)
