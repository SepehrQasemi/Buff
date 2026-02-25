from __future__ import annotations

import json
from pathlib import Path

import pytest

from s2.artifacts import (
    S2ArtifactError,
    S2ArtifactRequest,
    run_s2_artifact_pack,
    validate_s2_artifact_pack,
)
from s2.core import S2CoreConfig
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


def test_double_run_identical_inputs_identical_digests(tmp_path: Path) -> None:
    data_path = tmp_path / "bars.csv"
    _write_sample_csv(data_path)

    request = _request(data_path)
    run_a = run_s2_artifact_pack(request, tmp_path / "out_a")
    run_b = run_s2_artifact_pack(request, tmp_path / "out_b")

    digests_a = (run_a / "run_digests.json").read_bytes()
    digests_b = (run_b / "run_digests.json").read_bytes()
    assert digests_a == digests_b

    manifest_a = (run_a / "paper_run_manifest.json").read_bytes()
    manifest_b = (run_b / "paper_run_manifest.json").read_bytes()
    assert manifest_a == manifest_b

    validated_a = validate_s2_artifact_pack(run_a)
    validated_b = validate_s2_artifact_pack(run_b)
    assert validated_a["artifact_sha256"] == validated_b["artifact_sha256"]
    assert (
        validated_a["replay_identity_digest_sha256"] == validated_b["replay_identity_digest_sha256"]
    )


def test_missing_critical_input_fails_closed(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.csv"
    request = _request(missing_path)
    with pytest.raises(S2ArtifactError, match="INPUT_MISSING"):
        run_s2_artifact_pack(request, tmp_path / "out")


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


def test_schema_validation_fail_closed(tmp_path: Path) -> None:
    data_path = tmp_path / "bars.csv"
    _write_sample_csv(data_path)
    run_dir = run_s2_artifact_pack(_request(data_path), tmp_path / "out")

    manifest_path = run_dir / "paper_run_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload.pop("strategy", None)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

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

    with pytest.raises(S2ArtifactError, match="DIGEST_MISMATCH"):
        validate_s2_artifact_pack(run_dir)
