from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from s3.canonical import canonical_json_bytes, sha256_hex_bytes
from s3.runner import run_simulation_request


def _write_request(path: Path) -> None:
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
    request = {
        "artifact_ref": "runs/sample/manifest.json",
        "artifact_sha256": "a" * 64,
        "config": config,
        "config_sha256": sha256_hex_bytes(canonical_json_bytes(config)),
        "dataset_ref": "datasets/sample.parquet",
        "dataset_sha256": "b" * 64,
        "engine": {
            "build_sha": "7f353b9655a41fc628c83aba3102d0092563026b",
            "name": "buff-sim",
            "version": "1.0.0",
        },
        "schema_version": "s3.simulation_run_request.v1",
        "seed": 42,
        "tenant_id": "alice",
    }
    path.write_text(json.dumps(request, sort_keys=True), encoding="utf-8")


def test_s3_double_run_compare(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    _write_request(request_path)

    run_dir_a = run_simulation_request(request_path, tmp_path / "out_a")
    run_dir_b = run_simulation_request(request_path, tmp_path / "out_b")

    digests_a = (run_dir_a / "digests.json").read_bytes()
    digests_b = (run_dir_b / "digests.json").read_bytes()
    assert digests_a == digests_b

    result_a = (run_dir_a / "result.json").read_bytes()
    result_b = (run_dir_b / "result.json").read_bytes()
    assert result_a == result_b

    event_log_a = (run_dir_a / "event_log.jsonl").read_text(encoding="utf-8")
    event_log_b = (run_dir_b / "event_log.jsonl").read_text(encoding="utf-8")
    assert event_log_a == event_log_b
