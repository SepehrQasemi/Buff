from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from s3.canonical import canonical_json_bytes, sha256_hex_bytes
from s3.runner import S3RunnerError, run_simulation_request


def _build_request(
    request_path: Path,
    artifact_ref: str,
    artifact_sha256: str,
    dataset_ref: str,
    dataset_sha256: str,
) -> None:
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
        "artifact_ref": artifact_ref,
        "artifact_sha256": artifact_sha256,
        "config": config,
        "config_sha256": sha256_hex_bytes(canonical_json_bytes(config)),
        "dataset_ref": dataset_ref,
        "dataset_sha256": dataset_sha256,
        "engine": {"name": "buff-sim", "version": "1.0.0"},
        "schema_version": "s3.simulation_run_request.v1",
        "seed": 7,
        "tenant_id": "alice",
    }
    request_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_s3_input_digest_verification_match_passes(tmp_path: Path) -> None:
    artifact_bytes = b"artifact-input-v2"
    dataset_bytes = b"dataset-input-v2"
    (tmp_path / "artifact.bin").write_bytes(artifact_bytes)
    (tmp_path / "dataset.bin").write_bytes(dataset_bytes)

    request_path = tmp_path / "request_ok.json"
    _build_request(
        request_path=request_path,
        artifact_ref="artifact.bin",
        artifact_sha256=sha256_hex_bytes(artifact_bytes),
        dataset_ref="dataset.bin",
        dataset_sha256=sha256_hex_bytes(dataset_bytes),
    )

    run_dir = run_simulation_request(request_path, tmp_path / "out_ok")
    assert run_dir.exists()
    assert (run_dir / "result.json").exists()
    assert (run_dir / "digests.json").exists()


def test_s3_input_digest_verification_mismatch_fails_closed(tmp_path: Path) -> None:
    artifact_bytes = b"artifact-input-v2"
    dataset_bytes = b"dataset-input-v2"
    (tmp_path / "artifact.bin").write_bytes(artifact_bytes)
    (tmp_path / "dataset.bin").write_bytes(dataset_bytes)

    request_path = tmp_path / "request_bad.json"
    _build_request(
        request_path=request_path,
        artifact_ref="artifact.bin",
        artifact_sha256="0" * 64,
        dataset_ref="dataset.bin",
        dataset_sha256=sha256_hex_bytes(dataset_bytes),
    )

    output_root = tmp_path / "out_bad"
    with pytest.raises(S3RunnerError) as exc_info:
        run_simulation_request(request_path, output_root)

    err = exc_info.value
    assert err.code == "INPUT_DIGEST_MISMATCH"
    assert err.details.get("field") == "artifact_sha256"
    assert not output_root.exists()
