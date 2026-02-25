from __future__ import annotations

import json
from pathlib import Path

import pytest

import s2.artifacts as artifacts_module
from s2.artifacts import (
    REQUIRED_FAILURE_ARTIFACTS,
    REQUIRED_ARTIFACTS,
    RUN_STATUS_FAILED,
    RUN_STATUS_SUCCEEDED,
    S2ArtifactError,
    S2ArtifactRequest,
    run_s2_artifact_pack,
    validate_s2_artifact_pack,
)
from s2.canonical import (
    NUMERIC_POLICY,
    NUMERIC_POLICY_DIGEST_SHA256,
    NUMERIC_POLICY_ID,
    canonical_json_text,
)
from s2.core import S2CoreConfig, S2CoreResult
from s2.failure import resolve_error_code
from s2.models import FeeModel, FundingModel, LiquidationModel, SlippageBucket, SlippageModel


def _write_sample_csv(path: Path) -> None:
    path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2026-02-01T00:00:00Z,100,101,99,100.5,10\n"
        "2026-02-01T00:01:00Z,100.5,101.5,100,101.0,11\n"
        "2026-02-01T00:02:00Z,101.0,101.8,100.8,101.2,12\n"
        "2026-02-01T00:03:00Z,101.2,101.4,100.6,100.9,9\n",
        encoding="utf-8",
    )


def _request(data_path: Path) -> S2ArtifactRequest:
    return S2ArtifactRequest(
        run_id="s2run001",
        symbol="BTCUSDT",
        timeframe="1m",
        seed=11,
        data_path=str(data_path),
        strategy_version="strategy.demo.v1",
        strategy_config={"actions": ["LONG", "HOLD", "FLAT", "HOLD"]},
        risk_version="risk.demo.v1",
        risk_config={"blocked_event_seqs": []},
        core_config=S2CoreConfig(
            symbol="BTCUSDT",
            timeframe="1m",
            seed=11,
            initial_cash_quote=10_000.0,
            target_position_qty=1.0,
            fee_model=FeeModel(maker_bps=0.0, taker_bps=5.0),
            slippage_model=SlippageModel(
                buckets=(SlippageBucket(max_notional_quote=None, bps=2.0),)
            ),
            funding_model=FundingModel(interval_minutes=0),
            liquidation_model=LiquidationModel(
                maintenance_margin_ratio=0.005, conservative_buffer_ratio=0.1
            ),
        ),
    )


def _funding_gap_request(data_path: Path) -> S2ArtifactRequest:
    return S2ArtifactRequest(
        run_id="s2fail001",
        symbol="BTCUSDT",
        timeframe="1m",
        seed=17,
        data_path=str(data_path),
        strategy_version="strategy.demo.v1",
        strategy_config={"actions": ["LONG", "HOLD", "HOLD", "HOLD"]},
        risk_version="risk.demo.v1",
        risk_config={},
        core_config=S2CoreConfig(
            symbol="BTCUSDT",
            timeframe="1m",
            seed=17,
            initial_cash_quote=10_000.0,
            target_position_qty=1.0,
            fee_model=FeeModel(maker_bps=0.0, taker_bps=0.0),
            slippage_model=SlippageModel(
                buckets=(SlippageBucket(max_notional_quote=None, bps=0.0),)
            ),
            funding_model=FundingModel(
                interval_minutes=1,
                rates_by_ts_utc={
                    "2026-02-01T00:00:00Z": 0.001,
                    "2026-02-01T00:02:00Z": 0.001,
                    "2026-02-01T00:03:00Z": 0.001,
                },
            ),
            liquidation_model=LiquidationModel(
                maintenance_margin_ratio=0.005, conservative_buffer_ratio=0.1
            ),
        ),
    )


def _recompute_pack_manifest_and_run_digests(
    *,
    run_dir: Path,
    request: S2ArtifactRequest,
    artifacts: tuple[str, ...],
    run_status: str,
) -> None:
    pack_manifest = artifacts_module._build_artifact_pack_manifest(
        request.run_id,
        run_dir,
        artifacts=artifacts,
        run_status=run_status,
    )
    artifacts_module.write_canonical_json(run_dir / "artifact_pack_manifest.json", pack_manifest)

    artifact_digests = {
        name: artifacts_module.sha256_hex_file(run_dir / name)
        for name in sorted(artifacts)
        if name != "run_digests.json"
    }
    manifest_payload = json.loads((run_dir / "paper_run_manifest.json").read_text(encoding="utf-8"))
    replay_digest = str(manifest_payload["replay_identity"]["digest_sha256"])
    run_digests_payload = {
        "schema_version": artifacts_module.RUN_DIGESTS_SCHEMA,
        "numeric_policy_id": NUMERIC_POLICY_ID,
        "numeric_policy_digest_sha256": NUMERIC_POLICY_DIGEST_SHA256,
        "run_id": request.run_id,
        "artifact_sha256": artifact_digests,
        "artifact_pack_root_hash": pack_manifest["root_hash"],
        "artifact_pack_files_sha256": {
            str(row["path"]): str(row["sha256"]) for row in pack_manifest["files"]
        },
        "replay_identity_digest_sha256": replay_digest,
    }
    artifacts_module.write_canonical_json(run_dir / "run_digests.json", run_digests_payload)


def test_double_run_identical_inputs_identical_artifact_bytes_and_digests(tmp_path: Path) -> None:
    data_path = tmp_path / "bars.csv"
    _write_sample_csv(data_path)

    request = _request(data_path)
    run_a = run_s2_artifact_pack(request, tmp_path / "out_a")
    run_b = run_s2_artifact_pack(request, tmp_path / "out_b")

    files_a = sorted(path.name for path in run_a.iterdir() if path.is_file())
    files_b = sorted(path.name for path in run_b.iterdir() if path.is_file())
    assert files_a == files_b
    assert set(files_a) == set(REQUIRED_ARTIFACTS)

    for artifact_name in REQUIRED_ARTIFACTS:
        assert (run_a / artifact_name).read_bytes() == (run_b / artifact_name).read_bytes()

    validated_a = validate_s2_artifact_pack(run_a)
    validated_b = validate_s2_artifact_pack(run_b)
    assert validated_a["run_status"] == RUN_STATUS_SUCCEEDED
    assert validated_b["run_status"] == RUN_STATUS_SUCCEEDED
    assert validated_a["artifact_pack_root_hash"] == validated_b["artifact_pack_root_hash"]
    assert validated_a["artifact_pack_file_sha256"] == validated_b["artifact_pack_file_sha256"]
    assert validated_a["artifact_sha256"] == validated_b["artifact_sha256"]
    assert (
        validated_a["replay_identity_digest_sha256"] == validated_b["replay_identity_digest_sha256"]
    )
    assert not (run_a / "run_failure.json").exists()
    assert not (run_b / "run_failure.json").exists()

    for artifact_name in (
        "paper_run_manifest.json",
        "artifact_pack_manifest.json",
        "run_digests.json",
        "cost_breakdown.json",
    ):
        payload = json.loads((run_a / artifact_name).read_text(encoding="utf-8"))
        assert payload["numeric_policy_id"] == NUMERIC_POLICY_ID

    manifest_payload = json.loads((run_a / "paper_run_manifest.json").read_text(encoding="utf-8"))
    assert manifest_payload["numeric_policy"] == NUMERIC_POLICY
    assert manifest_payload["run_status"] == RUN_STATUS_SUCCEEDED
    run_digest_payload = json.loads((run_a / "run_digests.json").read_text(encoding="utf-8"))
    assert run_digest_payload["numeric_policy_digest_sha256"] == NUMERIC_POLICY_DIGEST_SHA256


def test_missing_critical_input_fails_closed(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.csv"
    request = _request(missing_path)
    with pytest.raises(S2ArtifactError, match="INPUT_MISSING"):
        run_s2_artifact_pack(request, tmp_path / "out")

    failure_dir = tmp_path / "out" / "s2run001"
    assert failure_dir.exists()
    validated = validate_s2_artifact_pack(failure_dir)
    assert validated["run_status"] == RUN_STATUS_FAILED
    assert set(path.name for path in failure_dir.iterdir() if path.is_file()) == set(
        REQUIRED_FAILURE_ARTIFACTS
    )
    run_failure = json.loads((failure_dir / "run_failure.json").read_text(encoding="utf-8"))
    assert run_failure["error"]["error_code"] == "INPUT_MISSING"
    assert run_failure["error"]["schema_version"] == "s2/error/v1"
    assert run_failure["numeric_policy_id"] == NUMERIC_POLICY_ID


def test_input_digest_validation_fail_closed(tmp_path: Path) -> None:
    data_path = tmp_path / "bars.csv"
    _write_sample_csv(data_path)
    request = S2ArtifactRequest(
        run_id="s2run001",
        symbol="BTCUSDT",
        timeframe="1m",
        seed=11,
        data_path=str(data_path),
        strategy_version="strategy.demo.v1",
        data_sha256="0" * 64,
        strategy_config={"actions": ["LONG", "HOLD", "FLAT", "HOLD"]},
        risk_version="risk.demo.v1",
        risk_config={"blocked_event_seqs": []},
        core_config=_request(data_path).core_config,
    )
    with pytest.raises(S2ArtifactError, match="INPUT_DIGEST_MISMATCH"):
        run_s2_artifact_pack(request, tmp_path / "out")

    failure_dir = tmp_path / "out" / "s2run001"
    run_failure = json.loads((failure_dir / "run_failure.json").read_text(encoding="utf-8"))
    assert run_failure["error"]["error_code"] == "DIGEST_MISMATCH"


def test_schema_validation_fail_closed(tmp_path: Path) -> None:
    data_path = tmp_path / "bars.csv"
    _write_sample_csv(data_path)
    request = _request(data_path)
    run_dir = run_s2_artifact_pack(request, tmp_path / "out")

    manifest_path = run_dir / "paper_run_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload.pop("strategy", None)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    _recompute_pack_manifest_and_run_digests(
        run_dir=run_dir,
        request=request,
        artifacts=REQUIRED_ARTIFACTS,
        run_status=RUN_STATUS_SUCCEEDED,
    )

    with pytest.raises(S2ArtifactError, match="SCHEMA_INVALID"):
        validate_s2_artifact_pack(run_dir)


def test_digest_validation_fail_closed(tmp_path: Path) -> None:
    data_path = tmp_path / "bars.csv"
    _write_sample_csv(data_path)
    run_dir = run_s2_artifact_pack(_request(data_path), tmp_path / "out")

    path = run_dir / "cost_breakdown.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["fees_quote"] = float(payload["fees_quote"]) + 1.0
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(S2ArtifactError) as excinfo:
        validate_s2_artifact_pack(run_dir)
    assert excinfo.value.code == "DIGEST_MISMATCH"


def test_missing_schema_version_row_fails_closed(tmp_path: Path) -> None:
    data_path = tmp_path / "bars.csv"
    _write_sample_csv(data_path)
    request = _request(data_path)
    run_dir = run_s2_artifact_pack(request, tmp_path / "out")

    path = run_dir / "decision_records.jsonl"
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    rows[0].pop("schema_version", None)
    path.write_bytes(
        ("\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n").encode("utf-8")
    )
    _recompute_pack_manifest_and_run_digests(
        run_dir=run_dir,
        request=request,
        artifacts=REQUIRED_ARTIFACTS,
        run_status=RUN_STATUS_SUCCEEDED,
    )

    with pytest.raises(S2ArtifactError, match="SCHEMA_INVALID"):
        validate_s2_artifact_pack(run_dir)


def test_wrong_schema_version_row_fails_closed(tmp_path: Path) -> None:
    data_path = tmp_path / "bars.csv"
    _write_sample_csv(data_path)
    request = _request(data_path)
    run_dir = run_s2_artifact_pack(request, tmp_path / "out")

    path = run_dir / "simulated_fills.jsonl"
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    rows[0]["schema_version"] = "s2/simulated_fills/v0"
    path.write_bytes(
        ("\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n").encode("utf-8")
    )
    _recompute_pack_manifest_and_run_digests(
        run_dir=run_dir,
        request=request,
        artifacts=REQUIRED_ARTIFACTS,
        run_status=RUN_STATUS_SUCCEEDED,
    )

    with pytest.raises(S2ArtifactError, match="SCHEMA_INVALID"):
        validate_s2_artifact_pack(run_dir)


def test_lf_utf8_and_path_determinism(tmp_path: Path) -> None:
    data_path = tmp_path / "bars.csv"
    _write_sample_csv(data_path)
    run_dir = run_s2_artifact_pack(_request(data_path), tmp_path / "out")

    for artifact_name in REQUIRED_ARTIFACTS:
        data = (run_dir / artifact_name).read_bytes()
        assert not data.startswith(b"\xef\xbb\xbf")
        assert b"\r" not in data
        data.decode("utf-8")

    manifest = json.loads((run_dir / "paper_run_manifest.json").read_text(encoding="utf-8"))
    data_ref = manifest["inputs"]["data_path"]
    assert isinstance(data_ref, str)
    assert "\\" not in data_ref
    assert ":\\" not in data_ref
    assert not data_ref.startswith("/")
    assert manifest["numeric_policy_id"] == NUMERIC_POLICY_ID

    jsonl_artifacts = [
        "decision_records.jsonl",
        "simulated_orders.jsonl",
        "simulated_fills.jsonl",
        "position_timeline.jsonl",
        "risk_events.jsonl",
        "funding_transfers.jsonl",
    ]
    for artifact_name in jsonl_artifacts:
        rows = [
            json.loads(line)
            for line in (run_dir / artifact_name).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert all(row["numeric_policy_id"] == NUMERIC_POLICY_ID for row in rows)


def test_float_canonicalization_is_stable() -> None:
    payload = {"a": 0.1 + 0.2, "b": [1.005, 1.00499999999999]}
    first = canonical_json_text(payload)
    second = canonical_json_text(payload)
    assert first == second
    assert first == '{"a":"0.30000000","b":["1.00500000","1.00500000"]}'


def test_jsonl_ordering_is_canonicalized(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data_path = tmp_path / "bars.csv"
    _write_sample_csv(data_path)
    request = _request(data_path)
    baseline = run_s2_artifact_pack(request, tmp_path / "out_a")
    original_core_loop = artifacts_module.run_s2_core_loop

    def _reordered_core_loop(*args, **kwargs):  # type: ignore[no-untyped-def]
        result = original_core_loop(*args, **kwargs)
        return S2CoreResult(
            seed=result.seed,
            decision_records=list(reversed(result.decision_records)),
            risk_checks=list(reversed(result.risk_checks)),
            simulated_orders=list(reversed(result.simulated_orders)),
            simulated_fills=list(reversed(result.simulated_fills)),
            position_timeline=list(reversed(result.position_timeline)),
            risk_events=list(reversed(result.risk_events)),
            funding_transfers=list(reversed(result.funding_transfers)),
            cost_breakdown=dict(result.cost_breakdown),
            final_state=dict(result.final_state),
        )

    monkeypatch.setattr(artifacts_module, "run_s2_core_loop", _reordered_core_loop)
    reordered = run_s2_artifact_pack(request, tmp_path / "out_b")

    for artifact_name in REQUIRED_ARTIFACTS:
        assert (baseline / artifact_name).read_bytes() == (reordered / artifact_name).read_bytes()


def test_missing_funding_window_writes_deterministic_run_failure(tmp_path: Path) -> None:
    data_path = tmp_path / "bars.csv"
    _write_sample_csv(data_path)
    request = _funding_gap_request(data_path)

    with pytest.raises(S2ArtifactError, match="MISSING_CRITICAL_FUNDING_WINDOW"):
        run_s2_artifact_pack(request, tmp_path / "out_a")
    with pytest.raises(S2ArtifactError, match="MISSING_CRITICAL_FUNDING_WINDOW"):
        run_s2_artifact_pack(request, tmp_path / "out_b")

    fail_a = tmp_path / "out_a" / "s2fail001"
    fail_b = tmp_path / "out_b" / "s2fail001"
    validated_a = validate_s2_artifact_pack(fail_a)
    validated_b = validate_s2_artifact_pack(fail_b)
    assert validated_a["run_status"] == RUN_STATUS_FAILED
    assert validated_b["run_status"] == RUN_STATUS_FAILED
    assert set(path.name for path in fail_a.iterdir() if path.is_file()) == set(
        REQUIRED_FAILURE_ARTIFACTS
    )
    assert set(path.name for path in fail_b.iterdir() if path.is_file()) == set(
        REQUIRED_FAILURE_ARTIFACTS
    )

    failure_bytes_a = (fail_a / "run_failure.json").read_bytes()
    failure_bytes_b = (fail_b / "run_failure.json").read_bytes()
    assert failure_bytes_a == failure_bytes_b

    run_failure = json.loads(failure_bytes_a.decode("utf-8"))
    assert run_failure["schema_version"] == "s2/run_failure/v1"
    assert run_failure["numeric_policy_id"] == NUMERIC_POLICY_ID
    assert run_failure["error"]["error_code"] == "MISSING_CRITICAL_FUNDING_WINDOW"
    assert run_failure["error"]["severity"] == "FATAL"
    assert run_failure["error"]["source"]["stage"] == "s2"
    assert "missing_funding_ts_utc" in run_failure["error"]["context"]


def test_schema_violation_writes_run_failure(tmp_path: Path) -> None:
    data_path = tmp_path / "bad_bars.csv"
    data_path.write_text(
        "timestamp,open,high,low,close,volume\n2026-02-01T00:00:00Z,100,101,99,,10\n",
        encoding="utf-8",
    )
    request = _request(data_path)
    with pytest.raises(S2ArtifactError, match="SCHEMA_INVALID"):
        run_s2_artifact_pack(request, tmp_path / "out")

    fail_dir = tmp_path / "out" / "s2run001"
    run_failure = json.loads((fail_dir / "run_failure.json").read_text(encoding="utf-8"))
    assert run_failure["error"]["error_code"] == "SCHEMA_INVALID"
    validate_s2_artifact_pack(fail_dir)


def test_numeric_policy_mismatch_fails_closed(tmp_path: Path) -> None:
    data_path = tmp_path / "bars.csv"
    _write_sample_csv(data_path)
    run_dir = run_s2_artifact_pack(_request(data_path), tmp_path / "out")

    path = run_dir / "artifact_pack_manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["numeric_policy_id"] = "s2/numeric/invalid/v1"
    path.write_bytes(
        (json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
    )

    with pytest.raises(S2ArtifactError, match="SCHEMA_INVALID"):
        validate_s2_artifact_pack(run_dir)


def test_float_token_in_jsonl_fails_closed_even_if_digests_recomputed(tmp_path: Path) -> None:
    data_path = tmp_path / "bars.csv"
    _write_sample_csv(data_path)
    request = _request(data_path)
    run_dir = run_s2_artifact_pack(request, tmp_path / "out")

    path = run_dir / "decision_records.jsonl"
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    rows[0]["seed"] = 11.125
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    _recompute_pack_manifest_and_run_digests(
        run_dir=run_dir,
        request=request,
        artifacts=REQUIRED_ARTIFACTS,
        run_status=RUN_STATUS_SUCCEEDED,
    )

    with pytest.raises(S2ArtifactError, match="float token") as excinfo:
        validate_s2_artifact_pack(run_dir)
    assert excinfo.value.code == "SCHEMA_INVALID"


def test_float_token_in_run_failure_context_fails_closed_even_if_digests_recomputed(
    tmp_path: Path,
) -> None:
    data_path = tmp_path / "bars.csv"
    _write_sample_csv(data_path)
    request = _funding_gap_request(data_path)

    with pytest.raises(S2ArtifactError, match="MISSING_CRITICAL_FUNDING_WINDOW"):
        run_s2_artifact_pack(request, tmp_path / "out")

    run_dir = tmp_path / "out" / "s2fail001"
    path = run_dir / "run_failure.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["error"]["context"]["probe_float"] = 1.2345
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _recompute_pack_manifest_and_run_digests(
        run_dir=run_dir,
        request=request,
        artifacts=REQUIRED_FAILURE_ARTIFACTS,
        run_status=RUN_STATUS_FAILED,
    )

    with pytest.raises(S2ArtifactError, match="float token") as excinfo:
        validate_s2_artifact_pack(run_dir)
    assert excinfo.value.code == "SCHEMA_INVALID"


def test_resolve_error_code_precedence_contract() -> None:
    assert (
        resolve_error_code(["MISSING_CRITICAL_FUNDING_WINDOW", "SCHEMA_INVALID"])
        == "SCHEMA_INVALID"
    )
    assert resolve_error_code(["unknown_code", "NOT_REAL", "DIGEST_MISMATCH"]) == "DIGEST_MISMATCH"


def test_failure_precedence_integration_uses_resolver(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data_path = tmp_path / "bars.csv"
    _write_sample_csv(data_path)
    request = S2ArtifactRequest(
        run_id="s2run001",
        symbol="BTCUSDT",
        timeframe="1m",
        seed=11,
        data_path=str(data_path),
        strategy_version="strategy.demo.v1",
        data_sha256="0" * 64,
        strategy_config={"actions": ["LONG", "HOLD", "FLAT", "HOLD"]},
        risk_version="risk.demo.v1",
        risk_config={"blocked_event_seqs": []},
        core_config=_request(data_path).core_config,
    )
    captured: dict[str, tuple[str, ...]] = {}
    real_resolver = artifacts_module.resolve_error_code

    def _capture(candidates: tuple[str, ...] | list[str]) -> str:
        captured["candidates"] = tuple(str(item) for item in candidates)
        return real_resolver(candidates)

    monkeypatch.setattr(artifacts_module, "resolve_error_code", _capture)

    with pytest.raises(S2ArtifactError, match="INPUT_DIGEST_MISMATCH"):
        run_s2_artifact_pack(request, tmp_path / "out")

    failure_dir = tmp_path / "out" / "s2run001"
    run_failure = json.loads((failure_dir / "run_failure.json").read_text(encoding="utf-8"))
    assert run_failure["error"]["error_code"] == "DIGEST_MISMATCH"
    assert set(captured["candidates"]) >= {"DIGEST_MISMATCH", "INPUT_DIGEST_MISMATCH"}


def test_failure_precedence_core_path_does_not_force_simulation_failed_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data_path = tmp_path / "bars.csv"
    _write_sample_csv(data_path)
    request = _funding_gap_request(data_path)
    captured: dict[str, tuple[str, ...]] = {}
    real_resolver = artifacts_module.resolve_error_code

    def _capture(candidates: tuple[str, ...] | list[str]) -> str:
        captured["candidates"] = tuple(str(item) for item in candidates)
        return real_resolver(candidates)

    monkeypatch.setattr(artifacts_module, "resolve_error_code", _capture)

    with pytest.raises(S2ArtifactError, match="MISSING_CRITICAL_FUNDING_WINDOW"):
        run_s2_artifact_pack(request, tmp_path / "out")

    assert captured["candidates"] == ("MISSING_CRITICAL_FUNDING_WINDOW",)
    assert "SIMULATION_FAILED" not in captured["candidates"]


def test_digest_check_precedes_json_parse(tmp_path: Path) -> None:
    data_path = tmp_path / "bars.csv"
    _write_sample_csv(data_path)
    run_dir = run_s2_artifact_pack(_request(data_path), tmp_path / "out")

    (run_dir / "decision_records.jsonl").write_bytes(b"{\n")

    with pytest.raises(S2ArtifactError) as excinfo:
        validate_s2_artifact_pack(run_dir)
    assert excinfo.value.code == "DIGEST_MISMATCH"


def test_invalid_json_with_recomputed_digests_fails_closed_schema_invalid(tmp_path: Path) -> None:
    data_path = tmp_path / "bars.csv"
    _write_sample_csv(data_path)
    request = _request(data_path)
    run_dir = run_s2_artifact_pack(request, tmp_path / "out")

    (run_dir / "decision_records.jsonl").write_bytes(b"{\n")
    _recompute_pack_manifest_and_run_digests(
        run_dir=run_dir,
        request=request,
        artifacts=REQUIRED_ARTIFACTS,
        run_status=RUN_STATUS_SUCCEEDED,
    )

    with pytest.raises(S2ArtifactError, match="SCHEMA_INVALID") as excinfo:
        validate_s2_artifact_pack(run_dir)
    assert excinfo.value.code == "SCHEMA_INVALID"
