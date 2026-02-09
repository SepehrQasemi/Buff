from __future__ import annotations

import argparse
from pathlib import Path

from .discovery import discover_plugins
from .validation import validate_all


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate user strategy/indicator plugins.")
    parser.add_argument(
        "--root",
        default=".",
        help="Repo root that contains user_indicators/ and user_strategies/.",
    )
    parser.add_argument(
        "--out",
        default="artifacts/plugins",
        help="Output directory for validation artifacts.",
    )
    args = parser.parse_args()

    root = Path(args.root)
    out_dir = Path(args.out)
    candidates = discover_plugins(root)
    results = validate_all(candidates, out_dir)
    passed = sum(result.status == "PASS" for result in results)
    failed = len(results) - passed
    print(f"plugins_found={len(results)} passed={passed} failed={failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
