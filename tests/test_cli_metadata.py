"""CLI metadata test."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pandas as pd

from buff import cli


def _is_hex(value: str) -> bool:
    try:
        int(value, 16)
    except ValueError:
        return False
    return len(value) == 64


def test_cli_metadata(tmp_path: Path) -> None:
    source = Path("tests/goldens/expected.csv")
    input_path = tmp_path / "expected.csv"
    shutil.copyfile(source, input_path)

    output_path = tmp_path / "output.parquet"
    meta_path = Path(f"{output_path}.meta.json")

    argv = ["buff", "features", str(input_path), str(output_path)]
    original_argv = sys.argv
    try:
        sys.argv = argv
        cli.main()
    finally:
        sys.argv = original_argv

    assert output_path.exists()
    assert meta_path.exists()

    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["features"] == ["ema_20", "rsi_14", "atr_14"]

    output_df = pd.read_parquet(output_path, engine="pyarrow")
    assert payload["row_count"] == int(output_df.shape[0])
    assert payload["row_count"] > 0

    assert _is_hex(payload["input_sha256"])
    assert _is_hex(payload["output_sha256"])

    assert payload["columns"] == ["ema_20", "rsi_14", "atr_14"]

    git_sha = payload.get("git_sha")
    assert git_sha is None or (len(git_sha) == 40 and all(ch in "0123456789abcdef" for ch in git_sha.lower()))
