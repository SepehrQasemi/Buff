from __future__ import annotations

import argparse
from pathlib import Path

from .artifacts import get_run_artifacts, list_runs


def main() -> None:
    parser = argparse.ArgumentParser(description="Chatbot artifact navigator")
    parser.add_argument("--workspaces", default="workspaces")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list-runs")

    show_parser = subparsers.add_parser("show-run")
    show_parser.add_argument("--run-id", required=True)

    args = parser.parse_args()
    workspaces_dir = Path(args.workspaces)

    if args.command == "list-runs":
        for run_id in list_runs(workspaces_dir):
            print(run_id)
    elif args.command == "show-run":
        artifacts = get_run_artifacts(args.run_id, workspaces_dir)
        print(artifacts.get("decision_records", ""))
        print(artifacts.get("report_md", ""))
        print(artifacts.get("report_summary", ""))
        print(artifacts.get("index", ""))


if __name__ == "__main__":
    main()
