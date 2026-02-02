"""CLI metadata test."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pandas as pd

from buff import cli
from buff.features.registry import FEATURES


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

    workspaces_dir = tmp_path / "workspaces"
    run_id = "demo-run"
    argv = ["buff", "features", str(input_path), str(output_path), "--run_id", run_id]
    original_argv = sys.argv
    original_workspaces = os.environ.get("BUFF_WORKSPACES_DIR")
    try:
        os.environ["BUFF_WORKSPACES_DIR"] = str(workspaces_dir)
        sys.argv = argv
        cli.main()
    finally:
        sys.argv = original_argv
        if original_workspaces is None:
            os.environ.pop("BUFF_WORKSPACES_DIR", None)
        else:
            os.environ["BUFF_WORKSPACES_DIR"] = original_workspaces

    assert output_path.exists()
    assert meta_path.exists()

    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    expected_features = list(FEATURES.keys())
    expected_columns = [col for spec in FEATURES.values() for col in spec["outputs"]]
    assert payload["features"] == expected_features

    output_df = pd.read_parquet(output_path, engine="pyarrow")
    assert payload["row_count"] == int(output_df.shape[0])
    assert payload["row_count"] > 0

    assert _is_hex(payload["input_sha256"])
    assert _is_hex(payload["output_sha256"])

    assert payload["columns"] == expected_columns

    git_sha = payload.get("git_sha")
    assert git_sha is None or (
        len(git_sha) == 40 and all(ch in "0123456789abcdef" for ch in git_sha.lower())
    )

    manifest_path = workspaces_dir / run_id / "feature_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["run_id"] == run_id
    features = manifest["features"]
    names = [entry["name"] for entry in features]
    assert names == sorted(names)
    for entry in features:
        assert set(entry.keys()) == {
            "name",
            "version",
            "params",
            "lookback",
            "dependencies",
            "outputs",
        }
        assert entry["dependencies"] == sorted(entry["dependencies"])
        assert entry["outputs"] == sorted(entry["outputs"])
