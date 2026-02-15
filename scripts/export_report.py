from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def _error_payload(
    code: str, message: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    normalized = details or {}
    payload = {"code": code, "message": message, "details": normalized}
    payload["error"] = {"code": code, "message": message, "details": normalized}
    return payload


def _fail(
    code: str, message: str, details: dict[str, Any] | None = None, exit_code: int = 1
) -> int:
    payload = _error_payload(code, message, details)
    sys.stderr.write(json.dumps(payload, sort_keys=True) + "\n")
    return exit_code


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(label)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label} invalid: {exc}") from exc


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload


def _safe_str(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _collect_manifest_artifacts(manifest: dict[str, Any]) -> list[str]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return []
    names: list[str] = []
    for key, value in artifacts.items():
        if key == "additional" and isinstance(value, list):
            names.extend([str(item) for item in value if item])
        elif isinstance(value, str):
            names.append(value)
    return sorted({name for name in names if name})


def _summarize_trades(trades_path: Path, limit: int = 5) -> dict[str, Any] | None:
    if not trades_path.exists():
        return None
    trades = list(_iter_jsonl(trades_path))
    if not trades:
        return {
            "count": 0,
            "wins": None,
            "losses": None,
            "flat": None,
            "samples": [],
        }
    wins = losses = flat = 0
    for trade in trades:
        pnl = trade.get("pnl")
        if pnl is None:
            continue
        try:
            pnl_value = float(pnl)
        except (TypeError, ValueError):
            continue
        if pnl_value > 0:
            wins += 1
        elif pnl_value < 0:
            losses += 1
        else:
            flat += 1
    samples = trades[:limit]
    return {
        "count": len(trades),
        "wins": wins if wins or losses or flat else None,
        "losses": losses if wins or losses or flat else None,
        "flat": flat if wins or losses or flat else None,
        "samples": samples,
    }


def _timeline_count(timeline_path: Path) -> int | None:
    if not timeline_path.exists():
        return None
    try:
        payload = _load_json(timeline_path, "timeline.json")
    except Exception:
        return None
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return len(payload["events"])
    if isinstance(payload, list):
        return len(payload)
    return None


def _decision_count(path: Path) -> int | None:
    if not path.exists():
        return None
    return sum(1 for _ in _iter_jsonl(path))


def _write_report(
    path: Path,
    *,
    run_id: str,
    manifest: dict[str, Any],
    metrics: dict[str, Any],
    trades_summary: dict[str, Any] | None,
    timeline_events: int | None,
    decision_count: int | None,
    artifacts: list[str],
    run_dir: Path,
) -> None:
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    manifest_run_id = manifest.get("run_id")
    manifest_inputs = manifest.get("inputs") if isinstance(manifest.get("inputs"), dict) else {}
    manifest_data = manifest.get("data") if isinstance(manifest.get("data"), dict) else {}

    lines: list[str] = []
    lines.append("# Run Report")
    lines.append("")
    lines.append(f"Generated: {created_at}")
    lines.append("")
    lines.append("## Run Metadata")
    lines.append(f"- Run ID: {run_id}")
    if manifest_run_id and manifest_run_id != run_id:
        lines.append(f"- Manifest Run ID: {manifest_run_id}")
    lines.append(f"- Status: {_safe_str(manifest.get('status'))}")
    lines.append(f"- Created At: {_safe_str(manifest.get('created_at'))}")
    lines.append(f"- Schema Version: {_safe_str(manifest.get('schema_version'))}")
    lines.append(f"- Engine Version: {_safe_str(manifest.get('engine_version'))}")
    lines.append(f"- Builder Version: {_safe_str(manifest.get('builder_version'))}")
    lines.append(f"- Inputs Hash: {_safe_str(manifest.get('inputs_hash'))}")
    lines.append("")
    lines.append("## Inputs Summary")
    lines.append(f"- Symbol: {_safe_str(manifest_data.get('symbol'))}")
    lines.append(f"- Timeframe: {_safe_str(manifest_data.get('timeframe'))}")
    lines.append(f"- Data Source: {_safe_str(manifest_data.get('source_path'))}")
    lines.append(f"- Strategy: {_safe_str((manifest.get('strategy') or {}).get('id'))}")
    lines.append(f"- Risk Level: {_safe_str((manifest.get('risk') or {}).get('level'))}")
    lines.append(
        f"- Costs (commission_bps): {_safe_str((manifest_inputs.get('costs') or {}).get('commission_bps'))}"
    )
    lines.append(
        f"- Costs (slippage_bps): {_safe_str((manifest_inputs.get('costs') or {}).get('slippage_bps'))}"
    )
    lines.append("")
    lines.append("## Key Metrics")
    metric_keys = [
        "total_return",
        "max_drawdown",
        "num_trades",
        "win_rate",
        "profit_factor",
        "sharpe",
        "sortino",
    ]
    for key in metric_keys:
        if key in metrics:
            lines.append(f"- {key}: {_safe_str(metrics.get(key))}")
    lines.append("")
    lines.append("## Trades Summary")
    if trades_summary is None:
        lines.append("- trades.jsonl not present.")
    else:
        lines.append(f"- Trade count: {trades_summary.get('count')}")
        if trades_summary.get("wins") is not None:
            lines.append(
                f"- Wins/Losses/Flat: {trades_summary.get('wins')}/"
                f"{trades_summary.get('losses')}/{trades_summary.get('flat')}"
            )
        samples = trades_summary.get("samples") or []
        if samples:
            lines.append("")
            lines.append("| timestamp | side | pnl | entry_price | exit_price |")
            lines.append("| --- | --- | --- | --- | --- |")
            for trade in samples:
                lines.append(
                    f"| {_safe_str(trade.get('timestamp'))} | {_safe_str(trade.get('side'))} | "
                    f"{_safe_str(trade.get('pnl'))} | {_safe_str(trade.get('entry_price'))} | "
                    f"{_safe_str(trade.get('exit_price'))} |"
                )
    lines.append("")
    lines.append("## Timeline / Decisions Summary")
    lines.append(f"- Timeline events: {_safe_str(timeline_events)}")
    lines.append(f"- Decision records: {_safe_str(decision_count)}")
    lines.append("")
    lines.append("## Artifact Inventory")
    lines.append("")
    lines.append("| Artifact | Present |")
    lines.append("| --- | --- |")
    for name in artifacts:
        present = (run_dir / name).exists()
        lines.append(f"| {name} | {'yes' if present else 'no'} |")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a run report from artifacts only.")
    parser.add_argument("--run-id", required=True, help="Run ID under RUNS_ROOT.")
    parser.add_argument("--runs-root", help="Override RUNS_ROOT.")
    parser.add_argument("--out", help="Output markdown path.")
    args = parser.parse_args()

    run_id = str(args.run_id).strip()
    if not run_id:
        return _fail("RUN_CONFIG_INVALID", "run-id is required", {"run_id": run_id})

    runs_root_value = args.runs_root or os.environ.get("RUNS_ROOT")
    if not runs_root_value:
        return _fail("RUNS_ROOT_UNSET", "RUNS_ROOT is not set", {"env": "RUNS_ROOT"})

    runs_root = Path(runs_root_value).expanduser().resolve()
    run_dir = (runs_root / run_id).resolve()
    if not run_dir.exists() or not run_dir.is_dir():
        return _fail(
            "RUN_NOT_FOUND", "Run not found", {"run_id": run_id, "runs_root": str(runs_root)}
        )

    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return _fail("RUN_CORRUPTED", "manifest.json missing", {"run_id": run_id})

    metrics_path = run_dir / "metrics.json"
    if not metrics_path.exists():
        return _fail("metrics_missing", "metrics.json missing", {"run_id": run_id})

    try:
        manifest = _load_json(manifest_path, "manifest.json")
    except FileNotFoundError:
        return _fail("RUN_CORRUPTED", "manifest.json missing", {"run_id": run_id})
    except RuntimeError as exc:
        return _fail("RUN_CORRUPTED", str(exc), {"run_id": run_id})

    try:
        metrics = _load_json(metrics_path, "metrics.json")
    except FileNotFoundError:
        return _fail("metrics_missing", "metrics.json missing", {"run_id": run_id})
    except RuntimeError as exc:
        return _fail("metrics_invalid", str(exc), {"run_id": run_id})

    trades_summary = _summarize_trades(run_dir / "trades.jsonl")
    timeline_events = _timeline_count(run_dir / "timeline.json")
    decision_count = _decision_count(run_dir / "decision_records.jsonl")
    artifacts = _collect_manifest_artifacts(manifest)

    out_path = Path(args.out) if args.out else run_dir / "report.md"
    _write_report(
        out_path,
        run_id=run_id,
        manifest=manifest,
        metrics=metrics,
        trades_summary=trades_summary,
        timeline_events=timeline_events,
        decision_count=decision_count,
        artifacts=artifacts,
        run_dir=run_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
