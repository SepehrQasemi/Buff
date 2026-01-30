from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from reports.decision_report import write_report


def list_run_dirs(workspaces_dir: Path) -> list[Path]:
    if not workspaces_dir.exists():
        return []
    runs = [path for path in workspaces_dir.iterdir() if path.is_dir()]
    return sorted(runs, key=lambda p: p.name)


def _relative_path(path: Path, base_dir: Path) -> str:
    try:
        return path.relative_to(base_dir).as_posix()
    except ValueError:
        return path.as_posix()


def _safe_load_summary(path: Path, run_id: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"status": "invalid", "run_id": run_id, "error": f"invalid_summary_json:{exc.msg}"}
    if not isinstance(data, dict):
        return {"status": "invalid", "run_id": run_id, "error": "invalid_summary_type"}
    data = dict(data)
    data.setdefault("run_id", run_id)
    data["status"] = "ok"
    return data


def load_run_summary(run_dir: Path) -> dict:
    run_id = run_dir.name
    workspaces_dir = run_dir.parent
    summary_path = run_dir / "report_summary.json"
    report_path = run_dir / "report.md"
    records_path = run_dir / "decision_records.jsonl"

    if summary_path.exists():
        if not report_path.exists():
            try:
                write_report(workspaces_dir, run_id)
            except Exception:
                pass
        summary = _safe_load_summary(summary_path, run_id)
        summary.setdefault("summary_path", _relative_path(summary_path, workspaces_dir))
        if report_path.exists():
            summary.setdefault("report_path", _relative_path(report_path, workspaces_dir))
        else:
            summary.setdefault("report_path", "")
        return summary

    if records_path.exists():
        try:
            outputs = write_report(run_dir.parent, run_id)
        except Exception as exc:
            # Keep error strings deterministic; avoid exception messages with line numbers.
            return {
                "status": "invalid",
                "run_id": run_id,
                "error": f"invalid_decision_records:{type(exc).__name__}",
            }
        summary = _safe_load_summary(summary_path, run_id)
        summary["summary_path"] = _relative_path(Path(outputs["report_summary"]), workspaces_dir)
        summary["report_path"] = _relative_path(Path(outputs["report_md"]), workspaces_dir)
        return summary

    return {"status": "empty", "run_id": run_id}


def _sorted_runs(runs: Iterable[dict]) -> list[dict]:
    return sorted(runs, key=lambda item: item.get("run_id", ""))


def build_index(workspaces_dir: Path) -> dict:
    runs = []
    for run_dir in list_run_dirs(workspaces_dir):
        summary = load_run_summary(run_dir)
        entry = {
            "run_id": summary.get("run_id", run_dir.name),
            "status": summary.get("status", "invalid"),
            "summary_path": summary.get("summary_path") or "",
            "report_path": summary.get("report_path") or "",
            "total": summary.get("total"),
            "executed": summary.get("executed"),
            "blocked": summary.get("blocked"),
            "error": summary.get("error"),
            "first_timestamp_utc": summary.get("first_timestamp_utc"),
            "last_timestamp_utc": summary.get("last_timestamp_utc"),
        }
        runs.append(entry)

    return {
        "schema_version": "1.0",
        "generated_at_utc": "N/A",
        "runs": _sorted_runs(runs),
    }


def render_index_markdown(index: dict) -> str:
    lines = ["# Workspace Index", "", "Generated deterministically from workspace artifacts.", ""]
    headers = [
        "run_id",
        "status",
        "total",
        "executed",
        "blocked",
        "error",
        "summary_path",
        "report_path",
    ]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

    def _display(value: object) -> str:
        if value is None or value == "":
            return "-"
        return str(value)

    for run in index.get("runs", []):
        row = [
            _display(run.get("run_id")),
            _display(run.get("status")),
            _display(run.get("total")),
            _display(run.get("executed")),
            _display(run.get("blocked")),
            _display(run.get("error")),
            _display(run.get("summary_path")),
            _display(run.get("report_path")),
        ]
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines) + "\n"


def write_index(workspaces_dir: Path) -> dict:
    index = build_index(workspaces_dir)
    index_path = workspaces_dir / "index.json"
    md_path = workspaces_dir / "index.md"
    workspaces_dir.mkdir(parents=True, exist_ok=True)

    index_path.write_text(
        json.dumps(index, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )
    md_path.write_text(render_index_markdown(index), encoding="utf-8")

    return {"index_json": str(index_path), "index_md": str(md_path)}
