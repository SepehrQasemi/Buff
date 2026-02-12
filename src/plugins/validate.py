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
        default="artifacts/plugin_validation",
        help="Output directory for validation artifacts.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a validation summary to stdout.",
    )
    args = parser.parse_args()

    root = Path(args.root)
    out_dir = Path(args.out)
    candidates = discover_plugins(root)
    results = validate_all(candidates, out_dir)
    valid = sum(result.status == "VALID" for result in results)
    invalid = len(results) - valid
    print(f"plugins_found={len(results)} valid={valid} invalid={invalid}")
    if args.summary:
        _print_summary(results)
    return 0


def _print_summary(results) -> None:
    reason_counts = {}
    invalid_items = []
    for result in results:
        if result.status == "VALID":
            continue
        codes = result.reason_codes
        invalid_items.append((result.plugin_type, result.plugin_id, codes))
        for code in codes:
            reason_counts[code] = reason_counts.get(code, 0) + 1

    top_codes = sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
    print("summary:")
    print(f"  total_plugins={len(results)}")
    print(f"  total_valid={sum(result.status == 'VALID' for result in results)}")
    print(f"  total_invalid={sum(result.status == 'INVALID' for result in results)}")
    print("  top_reason_codes:")
    if top_codes:
        for code, count in top_codes:
            print(f"    {code}: {count}")
    else:
        print("    (none)")
    print("  invalid_plugins:")
    if invalid_items:
        for plugin_type, plugin_id, codes in sorted(invalid_items):
            joined = ", ".join(codes) if codes else "(none)"
            print(f"    {plugin_type}:{plugin_id} -> {joined}")
    else:
        print("    (none)")


if __name__ == "__main__":
    raise SystemExit(main())
