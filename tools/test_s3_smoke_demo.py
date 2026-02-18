from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from s3.canonical import canonical_json_bytes, sha256_hex_bytes
from s3.runner import replay_simulation_result, run_simulation_request

REQUIRED_ARTIFACTS = {
    "manifest.json",
    "event_log.jsonl",
    "fills.jsonl",
    "result.json",
    "digests.json",
}

REQUIRED_DIGEST_KEYS = {
    "request_sha256",
    "result_sha256",
    "manifest_sha256",
    "event_log_sha256",
    "fills_sha256",
    "metrics_sha256",
    "report_sha256",
}


def _write_request(tmp_path: Path) -> Path:
    artifact_bytes = b"s3-smoke-artifact-v1"
    dataset_bytes = b"s3-smoke-dataset-v1"
    (tmp_path / "artifact.bin").write_bytes(artifact_bytes)
    (tmp_path / "dataset.bin").write_bytes(dataset_bytes)

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

    request_payload = {
        "artifact_ref": "artifact.bin",
        "artifact_sha256": sha256_hex_bytes(artifact_bytes),
        "config": config,
        "config_sha256": sha256_hex_bytes(canonical_json_bytes(config)),
        "dataset_ref": "dataset.bin",
        "dataset_sha256": sha256_hex_bytes(dataset_bytes),
        "engine": {"name": "buff-sim", "version": "1.0.0"},
        "schema_version": "s3.simulation_run_request.v1",
        "seed": 101,
        "tenant_id": "alice",
    }

    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request_payload, sort_keys=True), encoding="utf-8")
    return request_path


def test_s3_smoke_demo_end_to_end(tmp_path: Path) -> None:
    request_path = _write_request(tmp_path)

    run_dir_a = run_simulation_request(request_path, tmp_path / "out_a")
    run_dir_b = run_simulation_request(request_path, tmp_path / "out_b")
    assert run_dir_a.name == run_dir_b.name

    for artifact_name in REQUIRED_ARTIFACTS:
        assert (run_dir_a / artifact_name).exists()
        assert (run_dir_b / artifact_name).exists()

    digests_a_bytes = (run_dir_a / "digests.json").read_bytes()
    digests_b_bytes = (run_dir_b / "digests.json").read_bytes()
    assert digests_a_bytes == digests_b_bytes
    digests_payload = json.loads(digests_a_bytes.decode("utf-8"))
    assert REQUIRED_DIGEST_KEYS.issubset(set(digests_payload.keys()))

    result_a_bytes = (run_dir_a / "result.json").read_bytes()
    result_b_bytes = (run_dir_b / "result.json").read_bytes()
    assert result_a_bytes == result_b_bytes
    result_payload = json.loads(result_a_bytes.decode("utf-8"))

    replay_payload = replay_simulation_result(tmp_path / "out_a", "alice", run_dir_a.name)
    assert replay_payload == result_payload
    assert replay_payload["digests"] == digests_payload
