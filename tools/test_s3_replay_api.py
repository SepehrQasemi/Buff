from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from s3.canonical import canonical_json_bytes, sha256_hex_bytes
from s3.runner import S3RunnerError, replay_simulation_result, run_simulation_request


def _write_request(path: Path, tenant_id: str = "alice") -> None:
    artifact_bytes = b"artifact-replay-v1"
    dataset_bytes = b"dataset-replay-v1"
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
        "seed": 123,
        "tenant_id": tenant_id,
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_replay_simulation_result_success(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    _write_request(request_path, tenant_id="alice")
    runs_root = tmp_path / "runs"

    run_dir = run_simulation_request(request_path, runs_root)
    simulation_run_id = run_dir.name

    replayed = replay_simulation_result(runs_root, "alice", simulation_run_id)
    expected = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    assert replayed == expected


def test_replay_simulation_result_wrong_tenant_is_not_found(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    _write_request(request_path, tenant_id="alice")
    runs_root = tmp_path / "runs"

    run_dir = run_simulation_request(request_path, runs_root)
    simulation_run_id = run_dir.name

    with pytest.raises(S3RunnerError) as exc_info:
        replay_simulation_result(runs_root, "bob", simulation_run_id)
    err = exc_info.value
    assert err.code == "RUN_NOT_FOUND"


def test_replay_simulation_result_corruption_fails_closed(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    _write_request(request_path, tenant_id="alice")
    runs_root = tmp_path / "runs"

    run_dir = run_simulation_request(request_path, runs_root)
    simulation_run_id = run_dir.name
    (run_dir / "result.json").write_text("{not-json", encoding="utf-8")

    with pytest.raises(S3RunnerError) as exc_info:
        replay_simulation_result(runs_root, "alice", simulation_run_id)
    err = exc_info.value
    assert err.code == "RUN_CORRUPTED"
