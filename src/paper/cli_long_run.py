from __future__ import annotations

import argparse

from paper.long_run import LongRunConfig, run_long_paper


def main() -> int:
    parser = argparse.ArgumentParser(description="Long-run paper harness.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--duration-seconds", type=int, default=3600)
    parser.add_argument("--restart-every-seconds", type=int, default=300)
    parser.add_argument("--rotate-every-records", type=int, default=5000)
    parser.add_argument("--replay-every-records", type=int, default=2000)
    parser.add_argument("--feed", type=str, default=None)
    args = parser.parse_args()

    config = LongRunConfig(
        run_id=args.run_id,
        duration_seconds=args.duration_seconds,
        restart_every_seconds=args.restart_every_seconds,
        rotate_every_records=args.rotate_every_records,
        replay_every_records=args.replay_every_records,
        feed_path=args.feed,
    )

    try:
        summary = run_long_paper(config)
        print(summary)
        return 0
    except RuntimeError:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
