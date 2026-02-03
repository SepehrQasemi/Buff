"""CLI metadata test."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pandas as pd

from buff import cli
from buff.features.canonical import canonical_json_str
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
    meta_path = output_path.with_suffix(".meta.json")

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
    assert payload["schema_version"] == 1
    expected_features = sorted(FEATURES.keys())
    expected_columns = [col for name in expected_features for col in FEATURES[name]["outputs"]]
    feature_specs = payload["features"]
    assert [spec["feature_id"] for spec in feature_specs] == expected_features

    output_df = pd.read_parquet(output_path, engine="pyarrow")
    assert output_df.shape[0] > 0

    assert _is_hex(payload["source_fingerprint"])
    assert _is_hex(payload["bundle_fingerprint"])

    output_columns = ["timestamp"] + expected_columns
    assert list(output_df.columns) == output_columns

    git_sha = payload.get("code_fingerprint")
    assert git_sha == "unknown" or (
        len(git_sha) == 40 and all(ch in "0123456789abcdef" for ch in git_sha.lower())
    )

    manifest_path = workspaces_dir / run_id / "feature_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 2
    assert manifest["run_id"] == run_id
    features = manifest["features"]
    names = [entry["feature_id"] for entry in features]
    assert names == expected_features
    for entry in features:
        assert set(entry.keys()) == {
            "schema_version",
            "feature_id",
            "version",
            "description",
            "params_canonical_json",
            "lookback",
            "lookback_timedelta",
            "requires",
            "dependencies",
            "outputs",
            "output_dtypes",
            "input_timeframe",
        }
        assert entry["schema_version"] == 2
        feature_id = entry["feature_id"]
        assert entry["requires"] == list(FEATURES[feature_id]["requires"])
        assert entry["outputs"] == list(FEATURES[feature_id]["outputs"])
        assert entry["params_canonical_json"] == canonical_json_str(FEATURES[feature_id]["params"])
