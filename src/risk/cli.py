"""CLI for generating risk timeline reports."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from risk.risk_state import (
    DEFAULT_EVENTS_PATH,
    DEFAULT_FREQ,
    compute_risk_timeline,
    load_events_from_json,
    parse_timestamp,
    write_risk_timeline_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a deterministic risk timeline report.")
    parser.add_argument("--events", default=str(DEFAULT_EVENTS_PATH), help="Path to events JSON.")
    parser.add_argument("--start", required=True, help="Start timestamp (ISO-8601).")
    parser.add_argument("--end", required=True, help="End timestamp (ISO-8601).")
    parser.add_argument("--freq", default=DEFAULT_FREQ, help="Sampling frequency, e.g. 1h.")
    parser.add_argument(
        "--out",
        default="reports/risk_timeline.json",
        help="Output path for the JSON timeline.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    events = load_events_from_json(args.events)
    start = parse_timestamp(args.start)
    end = parse_timestamp(args.end)
    timeline = compute_risk_timeline(events, start, end, freq=args.freq)
    write_risk_timeline_json(Path(args.out), timeline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
