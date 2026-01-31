"""CLI for running the fundamental risk engine against offline fixtures."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from .artifacts import write_latest
from .engine import FundamentalRiskEngine
from .providers.offline import OfflineSnapshotProvider


def _parse_timestamp(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fundamental risk permission layer")
    parser.add_argument("--rules", required=True, help="Path to fundamental risk rules YAML")
    parser.add_argument("--fixture", required=True, help="Path to offline snapshot fixture JSON")
    parser.add_argument("--at", required=True, help="ISO timestamp (e.g., 2026-01-01T00:00:00Z)")
    args = parser.parse_args()

    engine = FundamentalRiskEngine()
    engine.load_rules(args.rules)

    provider = OfflineSnapshotProvider(args.fixture)
    snapshot = provider.get_snapshot(_parse_timestamp(args.at))
    decision = engine.compute(snapshot)

    print(f"{decision.final_risk_state} {decision.size_multiplier}")

    write_latest(decision, Path("reports") / "fundamental_risk_latest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
