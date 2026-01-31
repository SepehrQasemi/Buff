from __future__ import annotations

import argparse
from pathlib import Path

from .indexer import list_run_dirs, load_run_summary, write_index


def _cmd_list(workspaces_dir: Path) -> None:
    for run_dir in list_run_dirs(workspaces_dir):
        print(run_dir.name)


def _cmd_show(workspaces_dir: Path, run_id: str) -> None:
    run_dir = workspaces_dir / run_id
    summary = load_run_summary(run_dir)
    print(f"run_id: {summary.get('run_id', run_id)}")
    print(f"status: {summary.get('status')}")
    if summary.get("summary_path"):
        print(f"summary_path: {summary.get('summary_path')}")
    if summary.get("report_path"):
        print(f"report_path: {summary.get('report_path')}")
    for key in ("total", "executed", "blocked", "error"):
        if key in summary:
            print(f"{key}: {summary.get(key)}")


def _cmd_index(workspaces_dir: Path) -> None:
    outputs = write_index(workspaces_dir)
    print(outputs["index_json"])
    print(outputs["index_md"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Workspace audit index")
    parser.add_argument("--workspaces", default="workspaces")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list")

    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("--run-id", required=True)

    subparsers.add_parser("index")

    args = parser.parse_args()
    workspaces_dir = Path(args.workspaces)

    if args.command == "list":
        _cmd_list(workspaces_dir)
    elif args.command == "show":
        _cmd_show(workspaces_dir, args.run_id)
    elif args.command == "index":
        _cmd_index(workspaces_dir)


if __name__ == "__main__":
    main()
