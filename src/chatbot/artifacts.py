from __future__ import annotations

import json
from pathlib import Path


def _load_index(workspaces_dir: Path) -> dict:
    index_path = workspaces_dir / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"missing_index:{index_path}")
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("invalid_index_json") from exc
    if not isinstance(data, dict) or "runs" not in data:
        raise ValueError("invalid_index_schema")
    if not isinstance(data["runs"], list):
        raise ValueError("invalid_index_runs")
    return data


def list_runs(workspaces_dir: Path = Path("workspaces")) -> list[str]:
    index = _load_index(workspaces_dir)
    run_ids = [run.get("run_id", "") for run in index["runs"] if isinstance(run, dict)]
    return sorted([run_id for run_id in run_ids if run_id])


def get_run_artifacts(run_id: str, workspaces_dir: Path = Path("workspaces")) -> dict:
    index = _load_index(workspaces_dir)
    run_entry = None
    for run in index["runs"]:
        if isinstance(run, dict) and run.get("run_id") == run_id:
            run_entry = run
            break

    base_rel = Path(workspaces_dir.name)
    index_path = workspaces_dir / "index.json"
    index_rel = (base_rel / "index.json").as_posix() if index_path.exists() else ""

    if run_entry is None:
        return {
            "run_id": run_id,
            "status": "unknown",
            "decision_records": "",
            "report_md": "",
            "report_summary": "",
            "index": "",
        }

    run_dir = workspaces_dir / run_id
    decision_path = run_dir / "decision_records.jsonl"
    report_path = run_dir / "report.md"
    summary_path = run_dir / "report_summary.json"

    def _rel(path: Path) -> str:
        return (base_rel / run_id / path.name).as_posix()

    return {
        "run_id": run_id,
        "status": run_entry.get("status", "unknown"),
        "decision_records": _rel(decision_path) if decision_path.exists() else "",
        "report_md": _rel(report_path) if report_path.exists() else "",
        "report_summary": _rel(summary_path) if summary_path.exists() else "",
        "index": index_rel,
    }
