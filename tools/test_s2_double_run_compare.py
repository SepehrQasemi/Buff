from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from s2.artifacts import (
    REQUIRED_ARTIFACTS,
    RUN_STATUS_SUCCEEDED,
    S2ArtifactRequest,
    run_s2_artifact_pack,
    validate_s2_artifact_pack,
)
from s2.canonical import NUMERIC_POLICY_ID
from s2.core import S2CoreConfig
from s2.models import FeeModel, FundingModel, SlippageBucket, SlippageModel


def test_s2_double_run_compare(tmp_path: Path) -> None:
    data_path = tmp_path / "bars.csv"
    data_path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2026-02-01T00:00:00Z,100,101,99,100.5,10\n"
        "2026-02-01T00:01:00Z,100.5,101,100,100.8,8\n"
        "2026-02-01T00:02:00Z,100.8,101.2,100.5,101.0,7\n",
        encoding="utf-8",
    )
    request = S2ArtifactRequest(
        run_id="double001",
        symbol="BTCUSDT",
        timeframe="1m",
        seed=42,
        data_path=str(data_path),
        strategy_version="strategy.demo.v1",
        strategy_config={"actions": ["LONG", "HOLD", "FLAT"]},
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
    assert (run_a / "run_failure.json").exists() is False
    assert (run_b / "run_failure.json").exists() is False
    assert validated_a["artifact_pack_root_hash"] == validated_b["artifact_pack_root_hash"]
    assert validated_a["artifact_pack_file_sha256"] == validated_b["artifact_pack_file_sha256"]
    assert validated_a["artifact_sha256"] == validated_b["artifact_sha256"]

    # Ensure numeric policy identifiers are part of serialized records.
    first_line = (run_a / "decision_records.jsonl").read_text(encoding="utf-8").splitlines()[0]
    assert f'"numeric_policy_id":"{NUMERIC_POLICY_ID}"' in first_line
