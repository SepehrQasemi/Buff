from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from audit.workspace_snapshot import create_workspace_manifest, verify_workspace_manifest
from buff.data.run_ingest import main as run_ingest_main


def test_run_ingest_writes_workspace_snapshot(tmp_path: Path) -> None:
    workspaces_dir = tmp_path / "workspaces"
    data_dir = tmp_path / "data" / "ohlcv"
    reports_dir = tmp_path / "reports"
    run_id = "run-1"

    argv = [
        "run_ingest",
        "--symbols",
        "BTC/USDT",
        "--base_timeframe",
        "1m",
        "--timeframes",
        "1m",
        "--offline",
        "--fixtures_dir",
        "tests/fixtures/ohlcv",
        "--data_dir",
        str(data_dir),
        "--reports_dir",
        str(reports_dir),
        "--run_id",
        run_id,
    ]
    original_argv = sys.argv
    original_workspaces = os.environ.get("BUFF_WORKSPACES_DIR")
    try:
        os.environ["BUFF_WORKSPACES_DIR"] = str(workspaces_dir)
        sys.argv = argv
        run_ingest_main()
    finally:
        sys.argv = original_argv
        if original_workspaces is None:
            os.environ.pop("BUFF_WORKSPACES_DIR", None)
        else:
            os.environ["BUFF_WORKSPACES_DIR"] = original_workspaces

    run_dir = workspaces_dir / run_id
    snapshot_path = run_dir / "ohlcv_1m.parquet"
    assert snapshot_path.exists()

    manifest_path = create_workspace_manifest(run_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = {entry["path"] for entry in manifest["entries"]}
    assert f"{run_id}/ohlcv_1m.parquet" in entries

    verify_workspace_manifest(manifest_path)
