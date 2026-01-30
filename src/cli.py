from __future__ import annotations

import argparse
import sys
from pathlib import Path

from chatbot.artifacts import get_run_artifacts, list_runs
from decision_records.schema import validate_decision_record
from reports.decision_report import load_decision_records, sanitize_run_id, write_report
from workspaces.indexer import write_index


def _error(message: str) -> None:
    print(message, file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Buff audit CLI")
    parser.add_argument("--workspaces", default="workspaces")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("index")
    subparsers.add_parser("list-runs")

    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("--run-id", required=True)

    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("--run-id", required=True)
    report_parser.add_argument("--last-n", type=int, default=50)

    validate_parser = subparsers.add_parser("validate-run")
    validate_parser.add_argument("--run-id", required=True)

    args = parser.parse_args()
    workspaces_dir = Path(args.workspaces)

    try:
        if args.command == "index":
            outputs = write_index(workspaces_dir)
            print(outputs.get("index_json", ""))
            print(outputs.get("index_md", ""))
            return

        if args.command == "list-runs":
            for run_id in list_runs(workspaces_dir):
                print(run_id)
            return

        if args.command == "show":
            artifacts = get_run_artifacts(args.run_id, workspaces_dir)
            print(artifacts.get("decision_records", ""))
            print(artifacts.get("report_md", ""))
            print(artifacts.get("report_summary", ""))
            print(artifacts.get("index", ""))
            return

        if args.command == "report":
            run_id = sanitize_run_id(args.run_id)
            outputs = write_report(workspaces_dir, run_id, last_n=args.last_n)
            print(outputs.get("report_md", ""))
            print(outputs.get("report_summary", ""))
            return

        if args.command == "validate-run":
            run_id = sanitize_run_id(args.run_id)
            records_path = workspaces_dir / run_id / "decision_records.jsonl"
            records = load_decision_records(records_path)
            for record in records:
                validate_decision_record(record)
            print("valid")
            return

    except Exception as exc:
        _error(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
