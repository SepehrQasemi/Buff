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
    "metrics.json",
    "result.json",
    "digests.json",
}


def _write_request(tmp_path: Path) -> Path:
    artifact_bytes = b"s4-risk-artifact-v1"
    dataset_bytes = b"s4-risk-dataset-v1"
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
        "seed": 202,
        "tenant_id": "alice",
    }

    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request_payload, sort_keys=True), encoding="utf-8")
    return request_path


def _extract_equivalent_risk_block(
    result_payload: dict[str, object], metrics_payload: dict[str, object]
) -> dict[str, object]:
    schema_version = result_payload.get("schema_version")
    assert isinstance(schema_version, str) and schema_version, "config_version missing"

    request_digest = result_payload.get("request_digest_sha256")
    digests = result_payload.get("digests")
    assert isinstance(digests, dict), "digests missing"
    digest_from_digests = digests.get("request_sha256")
    assert isinstance(request_digest, str) and request_digest, "inputs_digest missing"
    assert isinstance(digest_from_digests, str) and digest_from_digests, (
        "digests.request_sha256 missing"
    )
    assert request_digest == digest_from_digests, "inputs_digest is ambiguous"

    status = result_payload.get("status")
    assert isinstance(status, str) and status, "decision/permission missing"

    traces = result_payload.get("traces")
    assert isinstance(traces, dict) and traces, "audit payload missing"
    assert isinstance(traces.get("artifact_ref"), str) and traces["artifact_ref"], (
        "audit payload missing artifact_ref"
    )
    assert isinstance(traces.get("event_count"), int), "audit payload missing event_count"

    metric_values = metrics_payload.get("values")
    assert isinstance(metric_values, dict), "metrics.values missing"
    assert "risk.max_drawdown_e8" in metric_values, "risk metric missing"

    return {
        "config_version": schema_version,
        "inputs_digest": request_digest,
        "decision_or_permission": status,
        "reasons_or_audit_payload": traces,
    }


def test_s4_risk_artifact_presence_on_s3_smoke_path(tmp_path: Path) -> None:
    request_path = _write_request(tmp_path)
    output_root = tmp_path / "runs"

    run_dir = run_simulation_request(request_path, output_root)
    produced = {path.name for path in run_dir.iterdir() if path.is_file()}
    assert REQUIRED_ARTIFACTS.issubset(produced)

    replay_payload = replay_simulation_result(output_root, "alice", run_dir.name)
    result_payload = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    metrics_payload = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    event_rows = (run_dir / "event_log.jsonl").read_text(encoding="utf-8").splitlines()

    assert replay_payload == result_payload
    assert event_rows, "event_log.jsonl must contain audit trace rows"

    risk_block = _extract_equivalent_risk_block(result_payload, metrics_payload)
    assert set(risk_block.keys()) == {
        "config_version",
        "inputs_digest",
        "decision_or_permission",
        "reasons_or_audit_payload",
    }
