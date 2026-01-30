from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Iterable

from decision_records.schema import SCHEMA_VERSION, validate_decision_record


def load_decision_records(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"missing_decision_records:{path}")

    records: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid_json_line:{line_no}") from exc
            validate_decision_record(record)
            records.append(record)
    return records


def sanitize_run_id(run_id: str) -> str:
    if not run_id:
        raise ValueError("missing_run_id")
    for ch in run_id:
        if not (ch.isalnum() or ch in {"_", "-"}):
            raise ValueError("invalid_run_id")
    return run_id


def _sorted_counts(items: Iterable[str]) -> dict[str, int]:
    counts = Counter(items)
    return {key: counts[key] for key in sorted(counts.keys())}


def summarize_records(records: list[dict]) -> dict:
    if not records:
        raise ValueError("no_records")

    total = len(records)
    statuses = [record["execution_status"] for record in records]
    executed = sum(1 for status in statuses if status == "EXECUTED")
    blocked = sum(1 for status in statuses if status == "BLOCKED")
    errored = sum(1 for status in statuses if status == "ERROR")

    risk_status_counts = _sorted_counts(record["risk_status"] for record in records)
    execution_status_counts = _sorted_counts(statuses)
    strategy_counts = _sorted_counts(record["strategy"]["name"] for record in records)

    timestamps = [record["timestamp_utc"] for record in records]
    first_ts = min(timestamps)
    last_ts = max(timestamps)

    run_ids = sorted({record["run_id"] for record in records})

    return {
        "schema_version": SCHEMA_VERSION,
        "total": total,
        "executed": executed,
        "blocked": blocked,
        "error": errored,
        "risk_status_counts": risk_status_counts,
        "execution_status_counts": execution_status_counts,
        "strategy_counts": strategy_counts,
        "first_timestamp_utc": first_ts,
        "last_timestamp_utc": last_ts,
        "unique_run_ids": run_ids,
    }


def _format_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    header_line = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = "\n".join("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join([header_line, divider, body]) if rows else "\n".join([header_line, divider])


def _short_digest(value: str, length: int = 8) -> str:
    return value[:length] if value else ""


def render_markdown(summary: dict, records: list[dict], last_n: int = 50) -> str:
    run_ids = summary.get("unique_run_ids", [])
    run_id = run_ids[0] if run_ids else "unknown"
    header = [
        f"# Decision Report (run_id: {run_id})",
        "",
        f"Schema version: {summary.get('schema_version', SCHEMA_VERSION)}",
        f"Time range: {summary.get('first_timestamp_utc')} -> {summary.get('last_timestamp_utc')}",
        "",
    ]

    summary_table = _format_markdown_table(
        ["total", "executed", "blocked", "error"],
        [
            [
                str(summary.get("total", 0)),
                str(summary.get("executed", 0)),
                str(summary.get("blocked", 0)),
                str(summary.get("error", 0)),
            ]
        ],
    )

    def _counts_table(title: str, counts: dict[str, int]) -> str:
        rows = [[key, str(counts[key])] for key in sorted(counts.keys())]
        return "\n".join([f"## {title}", "", _format_markdown_table([title, "count"], rows), ""])

    risk_table = _counts_table("Risk Status", summary.get("risk_status_counts", {}))
    exec_table = _counts_table("Execution Status", summary.get("execution_status_counts", {}))
    strat_table = _counts_table("Strategy", summary.get("strategy_counts", {}))

    reason_counts = Counter(
        record.get("reason")
        for record in records
        if record.get("execution_status") in {"BLOCKED", "ERROR"}
    )
    reason_rows = [
        [reason, str(count)]
        for reason, count in sorted(
            reason_counts.items(), key=lambda item: (-item[1], item[0] or "")
        )
        if reason
    ]
    if not reason_rows:
        reason_rows = [["None", "0"]]

    reasons_section = "\n".join(
        ["## Blocked/Error Reasons (top)", "", _format_markdown_table(["reason", "count"], reason_rows), ""]
    )

    last_records = records[-last_n:] if last_n > 0 else records
    last_rows = []
    for record in last_records:
        strategy = record.get("strategy", {})
        last_rows.append(
            [
                record.get("timestamp_utc", ""),
                record.get("execution_status", ""),
                record.get("risk_status", ""),
                record.get("control_status", ""),
                f"{strategy.get('name', '')}@{strategy.get('version', '')}",
                record.get("reason") or "",
                _short_digest(record.get("inputs_digest", "")),
            ]
        )

    last_section = "\n".join(
        [
            f"## Last {len(last_rows)} Decisions",
            "",
            _format_markdown_table(
                [
                    "timestamp_utc",
                    "execution_status",
                    "risk_status",
                    "control_status",
                    "strategy",
                    "reason",
                    "inputs_digest",
                ],
                last_rows,
            ),
            "",
        ]
    )

    artifact_path = records[0].get("artifact_paths", {}).get("decision_records")
    artifact_section = "\n".join(
        ["## Artifacts", "", f"decision_records: `{artifact_path}`", ""]
    )

    return "\n".join(header) + "\n".join(
        [
            "## Summary",
            "",
            summary_table,
            "",
            risk_table,
            exec_table,
            strat_table,
            reasons_section,
            last_section,
            artifact_section,
        ]
    )


def write_report(workspace_dir: Path, run_id: str, last_n: int = 50) -> dict:
    run_id = sanitize_run_id(run_id)
    records_path = workspace_dir / run_id / "decision_records.jsonl"
    records = load_decision_records(records_path)
    summary = summarize_records(records)

    report_md = render_markdown(summary, records, last_n=last_n)
    report_path = workspace_dir / run_id / "report.md"
    summary_path = workspace_dir / run_id / "report_summary.json"

    report_path.write_text(report_md, encoding="utf-8")
    summary_path.write_text(
        json.dumps(summary, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "report_md": str(report_path),
        "report_summary": str(summary_path),
    }
