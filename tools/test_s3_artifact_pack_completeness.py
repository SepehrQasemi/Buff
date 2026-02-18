from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from s3.canonical import canonical_json_bytes, sha256_hex_bytes, sha256_hex_file
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

FILE_DIGEST_KEYS = {
    "manifest_sha256": "manifest.json",
    "event_log_sha256": "event_log.jsonl",
    "fills_sha256": "fills.jsonl",
    "metrics_sha256": "metrics.json",
    "report_sha256": "report_summary.json",
}


def _write_request(path: Path) -> None:
    artifact_bytes = b"artifact-pack-v1"
    dataset_bytes = b"dataset-pack-v1"
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
        "seed": 99,
        "tenant_id": "alice",
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_s3_artifact_pack_completeness() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="s3-pack-"))
    request_path = temp_root / "request.json"
    _write_request(request_path)
    output_root = temp_root / "runs"

    run_dir = run_simulation_request(request_path, output_root)

    produced = {path.name for path in run_dir.iterdir() if path.is_file()}
    assert REQUIRED_ARTIFACTS.issubset(produced)

    digests_payload = json.loads((run_dir / "digests.json").read_text(encoding="utf-8"))
    assert REQUIRED_DIGEST_KEYS.issubset(set(digests_payload.keys()))

    for digest_key, artifact_name in FILE_DIGEST_KEYS.items():
        artifact_path = run_dir / artifact_name
        assert artifact_path.exists()
        assert digests_payload[digest_key] == sha256_hex_file(artifact_path)

    simulation_run_id = run_dir.name
    replayed = replay_simulation_result(output_root, "alice", simulation_run_id)
    assert replayed["digests"]["request_sha256"] == digests_payload["request_sha256"]
    assert replayed["digests"]["result_sha256"] == digests_payload["result_sha256"]
