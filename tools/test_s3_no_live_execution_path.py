from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from s3.canonical import canonical_json_bytes, sha256_hex_bytes
from s3.runner import (
    S3RunnerError,
    _assert_no_live_execution_path,
    run_simulation_request,
)


def _write_request(path: Path, tenant_id: str = "alice") -> None:
    artifact_bytes = b"artifact-no-live-v1"
    dataset_bytes = b"dataset-no-live-v1"
    (path.parent / "artifact.bin").write_bytes(artifact_bytes)
    (path.parent / "dataset.bin").write_bytes(dataset_bytes)

    config = {
        "cash_scale": 8,
        "clock_source": "dataset_event_time",
        "event_order_key": "event_seq",
        "numeric_encoding": "fixed_e8_int",
        "price_scale": 8,
        "qty_scale": 8,
        "rounding_mode": "half_even",
        "timestamp_format": "epoch_ms",
    }
    payload = {
        "artifact_ref": "artifact.bin",
        "artifact_sha256": sha256_hex_bytes(artifact_bytes),
        "config": config,
        "config_sha256": sha256_hex_bytes(canonical_json_bytes(config)),
        "dataset_ref": "dataset.bin",
        "dataset_sha256": sha256_hex_bytes(dataset_bytes),
        "engine": {"name": "buff-sim", "version": "1.0.0"},
        "schema_version": "s3.simulation_run_request.v1",
        "seed": 11,
        "tenant_id": tenant_id,
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_s3_no_live_execution_path_runtime_is_clean() -> None:
    _assert_no_live_execution_path()


def test_s3_no_live_execution_path_blocks_forbidden_imports(tmp_path: Path) -> None:
    source_root = tmp_path / "fake_s3"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "bad.py").write_text(
        "from execution.brokers import LiveBroker\n",
        encoding="utf-8",
    )

    with pytest.raises(S3RunnerError) as exc_info:
        _assert_no_live_execution_path(source_root)
    err = exc_info.value
    assert err.code == "LIVE_EXECUTION_PATH_FORBIDDEN"
    assert err.details["violations"][0]["module"] == "execution.brokers"


def test_s3_no_live_execution_path_allows_simulation_runs(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    _write_request(request_path)
    output_root = tmp_path / "runs"

    run_dir = run_simulation_request(request_path, output_root)
    assert run_dir.exists()
