from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import pandas as pd

from chatbot.router import INTENTS, route_intent
from chatbot.tools import SafetyGuardError, enforce_read_only, load_json, load_parquet, load_text


@dataclass(frozen=True)
class ChatbotConfig:
    root_dir: Path = Path(".")
    trades_path: Path = Path("workspaces/latest/trades.parquet")
    selector_trace_path: Path = Path("workspaces/latest/selector_trace.json")
    risk_timeline_path: Path = Path("reports/risk_timeline.json")
    workspaces_index_path: Path = Path("workspaces/index.json")
    teaching_doc_path: Path = Path("docs/chatbot.md")
    prompts_dir: Path = Path("src/chatbot/prompts")


class Chatbot:
    def __init__(self, config: ChatbotConfig | None = None) -> None:
        self.config = config or ChatbotConfig()

    def respond(self, message: str, intent_hint: str | None = None) -> str:
        intent = route_intent(message, intent_hint)
        if intent not in INTENTS:
            return _format_unknown(
                [self.config.workspaces_index_path],
                self.config.root_dir,
                [self.config.workspaces_index_path],
            )

        try:
            enforce_read_only(message)
        except SafetyGuardError as exc:
            return _format_forbidden(str(exc), self.config.root_dir)

        if intent == "reporting":
            return generate_daily_summary(
                self.config.trades_path,
                self.config.selector_trace_path,
                self.config.risk_timeline_path,
                self.config.root_dir,
            )
        if intent == "auditing":
            return generate_audit_summary(self.config.workspaces_index_path, self.config.root_dir)
        return generate_teaching_response(self.config.teaching_doc_path, self.config.root_dir)


def generate_daily_summary(
    trades_path: Path,
    selector_trace_path: Path,
    risk_timeline_path: Path,
    root_dir: Path,
) -> str:
    missing = _missing_paths([trades_path, selector_trace_path, risk_timeline_path])
    if missing:
        return _format_unknown(
            missing, root_dir, [trades_path, selector_trace_path, risk_timeline_path]
        )

    try:
        trades_df = load_parquet(trades_path)
    except (FileNotFoundError, ValueError) as exc:
        return _format_invalid(str(exc), trades_path, root_dir)

    try:
        selector_trace = load_json(selector_trace_path)
    except (FileNotFoundError, ValueError) as exc:
        return _format_invalid(str(exc), selector_trace_path, root_dir)

    try:
        risk_timeline = load_json(risk_timeline_path)
    except (FileNotFoundError, ValueError) as exc:
        return _format_invalid(str(exc), risk_timeline_path, root_dir)

    if not isinstance(selector_trace, list):
        return _format_invalid("invalid_selector_trace", selector_trace_path, root_dir)
    if not isinstance(risk_timeline, list):
        return _format_invalid("invalid_risk_timeline", risk_timeline_path, root_dir)

    trades_summary = _summarize_trades(trades_df)
    selector_summary = _summarize_selector_trace(selector_trace)
    risk_summary = _summarize_risk_timeline(risk_timeline)

    time_range = _time_range(
        trades_summary.get("timestamps", []),
        selector_summary.get("timestamps", []),
        risk_summary.get("timestamps", []),
    )

    lines = [
        "# Daily Summary",
        "",
        f"Time range: {time_range}",
        "",
        "## Trades",
        f"total: {trades_summary['total']}",
        f"symbols: {trades_summary['symbols']}",
        f"sides: {trades_summary['sides']}",
        f"status: {trades_summary['status']}",
        f"qty_total: {trades_summary['qty_total']}",
        "",
        "## Selector",
        f"total: {selector_summary['total']}",
        f"strategy_id: {selector_summary['strategy_id']}",
        f"status: {selector_summary['status']}",
        "",
        "## Risk Timeline",
        f"points: {risk_summary['total']}",
        f"risk_state: {risk_summary['risk_state']}",
        f"latest: {risk_summary['latest']}",
        "",
        "## Artifacts",
        f"trades.parquet: `{_format_path(trades_path, root_dir)}`",
        f"selector_trace.json: `{_format_path(selector_trace_path, root_dir)}`",
        f"risk_timeline.json: `{_format_path(risk_timeline_path, root_dir)}`",
    ]

    return "\n".join(lines) + "\n"


def generate_audit_summary(workspaces_index_path: Path, root_dir: Path) -> str:
    missing = _missing_paths([workspaces_index_path])
    if missing:
        return _format_unknown(missing, root_dir, [workspaces_index_path])

    try:
        index = load_json(workspaces_index_path)
    except (FileNotFoundError, ValueError) as exc:
        return _format_invalid(str(exc), workspaces_index_path, root_dir)

    if not isinstance(index, dict) or "runs" not in index or not isinstance(index["runs"], list):
        return _format_invalid("invalid_workspace_index", workspaces_index_path, root_dir)

    runs = [run for run in index["runs"] if isinstance(run, dict)]
    run_ids = sorted({str(run.get("run_id", "")) for run in runs if run.get("run_id")})
    statuses = _count_values(str(run.get("status", "")) for run in runs)

    lines = [
        "# Audit Summary",
        "",
        f"runs: {len(run_ids)}",
        f"run_ids: {_format_counts(run_ids)}",
        f"status: {_format_counts_map(statuses)}",
        "",
        "## Artifacts",
        f"workspaces/index.json: `{_format_path(workspaces_index_path, root_dir)}`",
    ]

    return "\n".join(lines) + "\n"


def generate_teaching_response(teaching_doc_path: Path, root_dir: Path) -> str:
    missing = _missing_paths([teaching_doc_path])
    if missing:
        return _format_unknown(missing, root_dir, [teaching_doc_path])

    try:
        content = load_text(teaching_doc_path)
    except (FileNotFoundError, ValueError) as exc:
        return _format_invalid(str(exc), teaching_doc_path, root_dir)

    topics = _extract_teaching_topics(content)

    lines = [
        "# Teaching Guide",
        "",
        "Topics:",
        *[f"- {topic}" for topic in topics],
        "",
        "## Artifacts",
        f"docs/chatbot.md: `{_format_path(teaching_doc_path, root_dir)}`",
    ]

    return "\n".join(lines) + "\n"


def _summarize_trades(trades_df) -> dict:
    required = {"ts_utc", "symbol", "side", "status", "qty"}
    missing = required.difference(trades_df.columns)
    if missing:
        raise ValueError(f"missing_trade_columns:{','.join(sorted(missing))}")

    total = int(trades_df.shape[0])
    timestamps = _clean_values(trades_df["ts_utc"].tolist())
    symbol_counts = _count_values(_clean_values(trades_df["symbol"].tolist()))
    side_counts = _count_values(_clean_values(trades_df["side"].tolist()))
    status_counts = _count_values(_clean_values(trades_df["status"].tolist()))

    qty_series = pd.to_numeric(trades_df["qty"], errors="coerce").fillna(0.0)
    qty = float(qty_series.sum())

    return {
        "total": total,
        "timestamps": timestamps,
        "symbols": _format_counts_map(symbol_counts),
        "sides": _format_counts_map(side_counts),
        "status": _format_counts_map(status_counts),
        "qty_total": f"{qty:.4f}",
    }


def _summarize_selector_trace(trace: Sequence[Mapping[str, object]]) -> dict:
    timestamps: list[str] = []
    strategies: list[str] = []
    statuses: list[str] = []

    for entry in trace:
        if not isinstance(entry, Mapping):
            continue
        ts = str(entry.get("ts_utc", "")).strip()
        if ts:
            timestamps.append(ts)
        strategy = _extract_strategy_id(entry)
        if strategy:
            strategies.append(strategy)
        status = _extract_status(entry)
        if status:
            statuses.append(status)

    return {
        "total": len(trace),
        "timestamps": timestamps,
        "strategy_id": _format_counts_map(_count_values(strategies)),
        "status": _format_counts_map(_count_values(statuses)),
    }


def _summarize_risk_timeline(timeline: Sequence[Mapping[str, object]]) -> dict:
    timestamps: list[str] = []
    states: list[str] = []
    latest_state = "unknown"
    latest_ts = ""

    for idx, entry in enumerate(timeline):
        if not isinstance(entry, Mapping):
            continue
        ts = str(entry.get("ts_utc", "")).strip()
        if ts:
            timestamps.append(ts)
        state = str(entry.get("risk_state", "")).strip()
        if state:
            states.append(state)
        if ts:
            if (ts, idx) >= (latest_ts, 0):
                latest_ts = ts
                latest_state = state or latest_state

    latest = "unknown"
    if latest_ts:
        latest = f"{latest_state} @ {latest_ts}"

    return {
        "total": len(timeline),
        "timestamps": timestamps,
        "risk_state": _format_counts_map(_count_values(states)),
        "latest": latest,
    }


def _extract_strategy_id(entry: Mapping[str, object]) -> str:
    for key in ("strategy_id", "selected_strategy_id"):
        value = entry.get(key)
        if value:
            return str(value)
    selection = entry.get("selection")
    if isinstance(selection, Mapping):
        value = selection.get("strategy_id")
        if value:
            return str(value)
    return ""


def _extract_status(entry: Mapping[str, object]) -> str:
    value = entry.get("status")
    if value:
        return str(value)
    selection = entry.get("selection")
    if isinstance(selection, Mapping):
        value = selection.get("status")
        if value:
            return str(value)
    return ""


def _extract_teaching_topics(content: str) -> list[str]:
    topics: list[str] = []
    for line in content.splitlines():
        text = line.strip()
        if text.startswith("## "):
            topics.append(text.replace("## ", "", 1))
    return topics or ["architecture", "examples", "non-capabilities"]


def _count_values(values: Iterable[str]) -> dict[str, int]:
    counts = Counter(value for value in values if value)
    return {key: counts[key] for key in sorted(counts.keys())}


def _format_counts(values: Iterable[str]) -> str:
    items = sorted({value for value in values if value})
    return ", ".join(items) if items else "none"


def _format_counts_map(counts: Mapping[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{key}={counts[key]}" for key in sorted(counts.keys()))


def _clean_values(values: Iterable[object]) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            cleaned.append(text)
    return cleaned


def _time_range(*timestamp_lists: Iterable[str]) -> str:
    timestamps: list[str] = []
    for items in timestamp_lists:
        for value in items:
            if value:
                timestamps.append(value)
    if not timestamps:
        return "unknown"
    timestamps.sort()
    return f"{timestamps[0]} -> {timestamps[-1]}"


def _missing_paths(paths: Iterable[Path]) -> list[Path]:
    return [path for path in paths if not path.exists()]


def _format_path(path: Path, root_dir: Path) -> str:
    try:
        return path.resolve().relative_to(root_dir.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _format_unknown(
    missing: Sequence[Path],
    root_dir: Path,
    artifacts: Sequence[Path] | None = None,
) -> str:
    missing_paths = [_format_path(path, root_dir) for path in missing]
    label = "artifact" if len(missing_paths) == 1 else "artifacts"
    summary = ", ".join(missing_paths)
    lines = [f"unknown (missing {label}: {summary})", "", "## Artifacts"]
    artifact_paths = artifacts if artifacts is not None else missing
    lines.extend(f"- `{_format_path(path, root_dir)}`" for path in artifact_paths)
    return "\n".join(lines) + "\n"


def _format_invalid(reason: str, path: Path, root_dir: Path) -> str:
    formatted_path = _format_path(path, root_dir)
    lines = [
        f"unknown (invalid artifact: {formatted_path})",
        "",
        "reason:",
        f"- {reason}",
        "",
        "## Artifacts",
        f"- `{formatted_path}`",
    ]
    return "\n".join(lines) + "\n"


def _format_forbidden(reason: str, root_dir: Path) -> str:
    safety_doc = Path("EXECUTION_SAFETY.md")
    formatted_path = _format_path(safety_doc, root_dir)
    lines = [
        f"denied ({reason})",
        "",
        "## Artifacts",
        f"- `{formatted_path}`",
    ]
    return "\n".join(lines) + "\n"
