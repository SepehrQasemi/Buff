from __future__ import annotations

import argparse
from paper.paper_runner import PaperRunConfig, run_paper_smoke


def main() -> int:
    parser = argparse.ArgumentParser(description="Paper runner smoke pipeline.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--restart-every", type=int, default=50)
    args = parser.parse_args()

    config = PaperRunConfig(
        run_id=args.run_id,
        steps=args.steps,
        restart_every=args.restart_every,
    )

    try:
        summary = run_paper_smoke(config)
        print(summary)
        return 0
    except RuntimeError:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
