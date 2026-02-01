from __future__ import annotations

import json
import sys
from pathlib import Path

from audit.decision_record import DecisionRecord
from audit.replay import ReplayConfig, ReplayRunner
from audit.snapshot import Snapshot


def main() -> None:
    decision_path = Path("tests/fixtures/decision_payload.json")
    snapshot_path = Path("tests/fixtures/snapshot_payload.json")

    decision_payload = json.loads(decision_path.read_text(encoding="utf-8"))
    snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))

    record = DecisionRecord.from_dict(decision_payload)
    snapshot = Snapshot.from_dict(snapshot_payload)

    print("SELF_CHECK decision_record OK")
    print("SELF_CHECK snapshot OK")

    runner = ReplayRunner()
    print("SELF_CHECK mode=strict-core")
    report_core = runner.replay(record, snapshot, strict_core=True)
    if not report_core.matched:
        print("SELF_CHECK strict-core FAILED")
        sys.exit(1)
    print("SELF_CHECK strict-core OK")

    print("SELF_CHECK mode=strict-full")
    report_full = runner.replay(record, snapshot, strict_full=True)
    if not report_full.matched:
        print("SELF_CHECK strict-full FAILED")
        sys.exit(1)
    print("SELF_CHECK strict-full OK")

    print("SELF_CHECK mode=strict-full (metadata override ignored)")
    runner_diff = ReplayRunner(
        config=ReplayConfig(ts_utc_override="2026-02-01T01:00:00Z")
    )
    report_full_diff = runner_diff.replay(record, snapshot, strict_full=True)
    if not report_full_diff.matched:
        print("SELF_CHECK strict-full-diff FAILED")
        sys.exit(1)
    print("SELF_CHECK strict-full-diff OK")


if __name__ == "__main__":
    main()
