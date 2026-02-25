from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from s2.artifacts import (
    REQUIRED_ARTIFACTS,
    REQUIRED_FAILURE_ARTIFACTS,
    RUN_STATUS_FAILED,
    RUN_STATUS_SUCCEEDED,
    S2ArtifactRequest,
    S2ArtifactError,
    run_s2_artifact_pack,
    validate_s2_artifact_pack,
)
from s2.canonical import NUMERIC_POLICY, NUMERIC_POLICY_DIGEST_SHA256, NUMERIC_POLICY_ID
from s2.core import S2CoreConfig
from s2.models import FeeModel, FundingModel, SlippageBucket, SlippageModel


def test_s2_artifact_pack_completeness() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="s2-pack-"))
    data_path = temp_root / "bars.csv"
    data_path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2026-02-01T00:00:00Z,100,101,99,100.5,10\n"
        "2026-02-01T00:01:00Z,100.5,101,100,100.8,8\n",
        encoding="utf-8",
    )

    request = S2ArtifactRequest(
        run_id="pack001",
        symbol="BTCUSDT",
        timeframe="1m",
        seed=5,
        data_path=str(data_path),
        strategy_version="strategy.demo.v1",
        strategy_config={"actions": ["LONG", "FLAT"]},
        risk_version="risk.demo.v1",
        risk_config={},
        core_config=S2CoreConfig(
            fee_model=FeeModel(maker_bps=0.0, taker_bps=0.0),
            slippage_model=SlippageModel(
                buckets=(SlippageBucket(max_notional_quote=None, bps=0.0),)
            ),
            funding_model=FundingModel(interval_minutes=0),
        ),
    )

    run_dir = run_s2_artifact_pack(request, temp_root / "out")
    produced = {path.name for path in run_dir.iterdir() if path.is_file()}
    assert set(REQUIRED_ARTIFACTS).issubset(produced)

    validated = validate_s2_artifact_pack(run_dir)
    assert validated["run_status"] == RUN_STATUS_SUCCEEDED
    assert set(validated["artifact_sha256"].keys()) == {
        "paper_run_manifest.json",
        "decision_records.jsonl",
        "simulated_orders.jsonl",
        "simulated_fills.jsonl",
        "position_timeline.jsonl",
        "risk_events.jsonl",
        "funding_transfers.jsonl",
        "cost_breakdown.json",
        "artifact_pack_manifest.json",
    }
    assert len(validated["artifact_pack_root_hash"]) == 64

    pack_manifest = json.loads(
        (run_dir / "artifact_pack_manifest.json").read_text(encoding="utf-8")
    )
    run_digests = json.loads((run_dir / "run_digests.json").read_text(encoding="utf-8"))
    assert pack_manifest["root_hash"] == validated["artifact_pack_root_hash"]
    assert run_digests["artifact_pack_root_hash"] == validated["artifact_pack_root_hash"]
    assert pack_manifest["schema_version"] == "s2/artifact_pack_manifest/v1"
    assert run_digests["schema_version"] == "s2/run_digests/v1"
    assert pack_manifest["numeric_policy_id"] == NUMERIC_POLICY_ID
    assert pack_manifest["numeric_policy"] == NUMERIC_POLICY
    assert run_digests["numeric_policy_id"] == NUMERIC_POLICY_ID
    assert run_digests["numeric_policy_digest_sha256"] == NUMERIC_POLICY_DIGEST_SHA256
    manifest_payload = json.loads((run_dir / "paper_run_manifest.json").read_text(encoding="utf-8"))
    assert manifest_payload["schema_version"] == "s2/paper_run_manifest/v1"
    assert manifest_payload["numeric_policy_id"] == NUMERIC_POLICY_ID
    assert manifest_payload["numeric_policy"] == NUMERIC_POLICY
    assert manifest_payload["run_status"] == RUN_STATUS_SUCCEEDED
    assert "\\" not in manifest_payload["inputs"]["data_path"]
    assert ":\\" not in manifest_payload["inputs"]["data_path"]
    assert not manifest_payload["inputs"]["data_path"].startswith("/")
    assert not (run_dir / "run_failure.json").exists()
    assert (
        json.loads((run_dir / "cost_breakdown.json").read_text(encoding="utf-8"))["schema_version"]
        == "s2/cost_breakdown/v1"
    )
    assert (
        json.loads((run_dir / "cost_breakdown.json").read_text(encoding="utf-8"))[
            "numeric_policy_id"
        ]
        == NUMERIC_POLICY_ID
    )

    for path in run_dir.iterdir():
        if not path.is_file():
            continue
        data = path.read_bytes()
        assert not data.startswith(b"\xef\xbb\xbf")
        assert b"\r" not in data


def test_s2_failure_artifact_contract() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="s2-fail-pack-"))
    data_path = temp_root / "bars.csv"
    data_path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2026-02-01T00:00:00Z,100,101,99,100.5,10\n"
        "2026-02-01T00:01:00Z,100.5,101,100,100.8,8\n"
        "2026-02-01T00:02:00Z,100.8,101.2,100.5,101.0,7\n",
        encoding="utf-8",
    )
    request = S2ArtifactRequest(
        run_id="fail001",
        symbol="BTCUSDT",
        timeframe="1m",
        seed=9,
        data_path=str(data_path),
        strategy_version="strategy.demo.v1",
        strategy_config={"actions": ["LONG", "HOLD", "HOLD"]},
        risk_version="risk.demo.v1",
        risk_config={},
        core_config=S2CoreConfig(
            fee_model=FeeModel(maker_bps=0.0, taker_bps=0.0),
            slippage_model=SlippageModel(
                buckets=(SlippageBucket(max_notional_quote=None, bps=0.0),)
            ),
            funding_model=FundingModel(
                interval_minutes=1,
                rates_by_ts_utc={
                    "2026-02-01T00:00:00Z": 0.001,
                    "2026-02-01T00:02:00Z": 0.001,
                },
            ),
        ),
    )

    with pytest.raises(S2ArtifactError, match="MISSING_CRITICAL_FUNDING_WINDOW"):
        run_s2_artifact_pack(request, temp_root / "out")

    run_dir = temp_root / "out" / "fail001"
    produced = {path.name for path in run_dir.iterdir() if path.is_file()}
    assert set(REQUIRED_FAILURE_ARTIFACTS).issubset(produced)

    validated = validate_s2_artifact_pack(run_dir)
    assert validated["run_status"] == RUN_STATUS_FAILED
    run_failure = json.loads((run_dir / "run_failure.json").read_text(encoding="utf-8"))
    assert run_failure["error"]["error_code"] == "MISSING_CRITICAL_FUNDING_WINDOW"
    assert run_failure["error"]["severity"] == "FATAL"
