from __future__ import annotations

import argparse

from audit.replay import replay_verify


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay decision_records.jsonl and verify determinism."
    )
    parser.add_argument("--records", required=True, help="Path to decision_records.jsonl")
    args = parser.parse_args()

    result = replay_verify(records_path=args.records)

    print(f"TOTAL: {result.total}")
    print(f"MATCHED: {result.matched}")
    print(f"MISMATCHED: {result.mismatched}")
    print(f"HASH_MISMATCH: {result.hash_mismatch}")
    print(f"ERRORS: {result.errors}")


if __name__ == "__main__":
    main()
