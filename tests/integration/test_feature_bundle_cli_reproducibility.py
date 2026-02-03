from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

from buff.features.bundle import FEATURE_BUNDLE_PARQUET_NAME


def _run_cli(input_path: Path, out_dir: Path, repo_root: Path) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        "-m",
        "src.data.cli",
        "features",
        "--input",
        str(input_path),
        "--out",
        str(out_dir),
    ]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=repo_root)


def test_feature_bundle_cli_reproducible(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    fixture_path = repo_root / "tests/fixtures/ohlcv/ohlcv_1m_fixture.parquet"
    assert fixture_path.exists()

    out_dir_a = tmp_path / "run_a"
    out_dir_b = tmp_path / "run_b"

    result_a = _run_cli(fixture_path, out_dir_a, repo_root)
    result_b = _run_cli(fixture_path, out_dir_b, repo_root)

    assert result_a.returncode == 0, result_a.stderr
    assert result_b.returncode == 0, result_b.stderr

    parquet_a = out_dir_a / "features" / FEATURE_BUNDLE_PARQUET_NAME
    parquet_b = out_dir_b / "features" / FEATURE_BUNDLE_PARQUET_NAME
    meta_a = parquet_a.with_suffix(".meta.json")
    meta_b = parquet_b.with_suffix(".meta.json")

    df_a = pd.read_parquet(parquet_a, engine="pyarrow")
    df_b = pd.read_parquet(parquet_b, engine="pyarrow")
    assert df_a.equals(df_b)

    assert meta_a.read_bytes() == meta_b.read_bytes()
