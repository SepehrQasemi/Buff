from __future__ import annotations

import argparse
from pathlib import Path

from .decision_report import sanitize_run_id, write_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate decision record report")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--workspace", default="workspaces")
    parser.add_argument("--last-n", type=int, default=50)
    args = parser.parse_args()

    run_id = sanitize_run_id(args.run_id)
    workspace_dir = Path(args.workspace)
    outputs = write_report(workspace_dir, run_id, last_n=args.last_n)
    print(outputs["report_md"])
    print(outputs["report_summary"])


if __name__ == "__main__":
    main()
