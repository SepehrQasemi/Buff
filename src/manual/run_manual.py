"""Manual analysis mode CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from utils.path_guard import guard_manual_write


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual analysis mode session")
    parser.add_argument("--workspace", type=str, required=True, help="Workspace name")
    parser.add_argument("--symbol", type=str, required=True, help="Symbol (e.g., BTCUSDT)")
    parser.add_argument("--timeframe", type=str, required=True, help="Timeframe (e.g., 1h)")
    args = parser.parse_args()

    session = {
        "workspace": args.workspace,
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "indicator_params": {},
    }

    session_path = Path("workspaces") / args.workspace / "session.json"
    # All file writes MUST go through path_guard to preserve mode separation.
    target = guard_manual_write(session_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
