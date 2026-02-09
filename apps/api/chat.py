from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter
from pydantic import BaseModel, Field

from .artifacts import DecisionRecords, extract_run_metadata, find_timeline_path, get_artifacts_root
from .errors import raise_api_error
from .timeutils import format_ts, parse_ts

router = APIRouter()

_ALLOWED_INDICATOR_CATEGORIES = {
    "trend",
    "momentum",
    "volatility",
    "volume",
    "statistics",
    "structure",
}
_ALLOWED_STRATEGY_CATEGORIES = {
    "trend",
    "mr",
    "momentum",
    "volatility",
    "structure",
    "wrapper",
}
_ALLOWED_INTENTS = {
    "HOLD",
    "ENTER_LONG",
    "ENTER_SHORT",
    "EXIT_LONG",
    "EXIT_SHORT",
}
_ALLOWED_NAN_POLICIES = {"propagate", "fill", "error"}
_FORBIDDEN_IMPORT_ROOTS = {
    "os",
    "sys",
    "subprocess",
    "socket",
    "requests",
    "urllib",
    "http",
    "pathlib",
    "time",
    "random",
}
_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_TIMESTAMP_FIELDS = ("timestamp", "timestamp_utc", "ts_utc", "ts", "time", "date")


class ChatRequest(BaseModel):
    mode: str
    message: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class Step(BaseModel):
    id: str
    text: str


class FileTemplate(BaseModel):
    path: str
    contents: str


class Diagnostics(BaseModel):
    inputs: dict[str, Any]
    notes: list[str]


class ChatResponse(BaseModel):
    mode: str
    title: str
    summary: str
    steps: list[Step]
    files_to_create: list[FileTemplate]
    commands: list[str]
    success_criteria: list[str]
    warnings: list[str]
    blockers: list[str]
    diagnostics: Diagnostics


_MODE_INDEX = [
    {
        "mode": "add_indicator",
        "required_context": ["indicator_id", "name"],
        "optional_context": [
            "inputs",
            "outputs",
            "params",
            "warmup_bars",
            "nan_policy",
            "category",
            "version",
            "author",
        ],
    },
    {
        "mode": "add_strategy",
        "required_context": ["strategy_id", "name"],
        "optional_context": [
            "inputs",
            "indicators",
            "params",
            "warmup_bars",
            "category",
            "version",
            "author",
            "provides_confidence",
        ],
    },
    {
        "mode": "review_plugin",
        "required_context": ["kind", "id"],
        "optional_context": ["path_optional"],
    },
    {
        "mode": "explain_trade",
        "required_context": ["run_id", "trade_id_or_decision_id"],
        "optional_context": [],
    },
]


@router.get("/chat/modes")
def chat_modes() -> dict[str, list[dict[str, Any]]]:
    return {"modes": _MODE_INDEX}


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    mode = (request.mode or "").strip().lower()
    supported = {item["mode"] for item in _MODE_INDEX}
    if mode not in supported:
        raise_api_error(
            400,
            "chat_mode_invalid",
            "Unsupported chat mode",
            {"mode": request.mode, "supported": sorted(supported)},
        )

    if mode == "add_indicator":
        return _add_indicator(request)
    if mode == "add_strategy":
        return _add_strategy(request)
    if mode == "review_plugin":
        return _review_plugin(request)
    if mode == "explain_trade":
        return _explain_trade(request)

    raise_api_error(400, "chat_mode_invalid", "Unsupported chat mode", {"mode": request.mode})
    return _empty_response(mode, "unsupported")


def _add_indicator(request: ChatRequest) -> ChatResponse:
    context = request.context or {}
    notes: list[str] = []
    warnings: list[str] = []

    name = _pick_value(context, ["name", "indicator_name", "title"], "Custom Indicator")
    indicator_id, id_warning = _normalize_id(
        _pick_value(context, ["indicator_id", "id"], ""), "custom_indicator"
    )
    if id_warning:
        warnings.append(id_warning)
    if not indicator_id:
        indicator_id = _normalize_id(name, "custom_indicator")[0]
        warnings.append("indicator_id missing; using derived id.")

    inputs = _normalize_string_list(context.get("inputs"), ["close"])
    outputs = _normalize_string_list(context.get("outputs"), ["value"])
    params = _normalize_params(context.get("params"))
    warmup_bars = _normalize_int(context.get("warmup_bars"), params[0]["default"])
    nan_policy = _normalize_nan_policy(context.get("nan_policy"), warnings)
    category = _normalize_category(
        context.get("category"), _ALLOWED_INDICATOR_CATEGORIES, "momentum", warnings
    )
    version = _normalize_version(context.get("version"), warnings)
    author = _normalize_optional_str(context.get("author"))

    indicator_yaml = _render_indicator_yaml(
        indicator_id=indicator_id,
        name=name,
        version=version,
        author=author,
        category=category,
        inputs=inputs,
        outputs=outputs,
        params=params,
        warmup_bars=warmup_bars,
        nan_policy=nan_policy,
    )

    indicator_py = _render_indicator_py(outputs)

    steps = [
        _step("create_dir", f"Create directory user_indicators/{indicator_id}/."),
        _step(
            "write_yaml",
            "Fill indicator.yaml with required fields (template below).",
        ),
        _step(
            "write_py",
            "Implement compute(ctx) in indicator.py (template below).",
        ),
        _step(
            "validate",
            "Run the validator: python -m src.plugins.validate --out artifacts/plugins",
        ),
        _step("test", "Run ruff and pytest to confirm it passes."),
    ]

    files = [
        {
            "path": f"user_indicators/{indicator_id}/indicator.yaml",
            "contents": indicator_yaml,
        },
        {
            "path": f"user_indicators/{indicator_id}/indicator.py",
            "contents": indicator_py,
        },
    ]

    commands = [
        "python -m src.plugins.validate --out artifacts/plugins",
        "python -m ruff check .",
        "python -m pytest",
    ]
    success = [
        f"user_indicators/{indicator_id}/indicator.yaml exists",
        f"user_indicators/{indicator_id}/indicator.py exists",
        f"artifacts/plugins/indicator/{indicator_id}/validation.json status=PASS",
        "Indicator appears in the UI Indicators tab (validated plugins only).",
    ]
    warnings.extend(
        [
            "Indicator logic must be causal and deterministic.",
            "Do not access future data or perform I/O in compute(ctx).",
        ]
    )

    diagnostics = _diagnostics(request, notes)
    return ChatResponse(
        mode="add_indicator",
        title=f"Add Indicator: {name}",
        summary="Template files and validation steps for a new indicator.",
        steps=steps,
        files_to_create=[FileTemplate(**item) for item in files],
        commands=commands,
        success_criteria=success,
        warnings=warnings,
        blockers=[],
        diagnostics=diagnostics,
    )


def _add_strategy(request: ChatRequest) -> ChatResponse:
    context = request.context or {}
    notes: list[str] = []
    warnings: list[str] = []

    name = _pick_value(context, ["name", "strategy_name", "title"], "Custom Strategy")
    strategy_id, id_warning = _normalize_id(
        _pick_value(context, ["strategy_id", "id"], ""), "custom_strategy"
    )
    if id_warning:
        warnings.append(id_warning)
    if not strategy_id:
        strategy_id = _normalize_id(name, "custom_strategy")[0]
        warnings.append("strategy_id missing; using derived id.")

    series_inputs = _normalize_string_list(context.get("inputs"), ["close"])
    indicators = _normalize_string_list(context.get("indicators"), [])
    params = _normalize_params(
        context.get("params"),
        default_name="threshold",
        default_type="float",
    )
    warmup_bars = _normalize_int(context.get("warmup_bars"), 20)
    provides_confidence = bool(context.get("provides_confidence", False))
    category = _normalize_category(
        context.get("category"), _ALLOWED_STRATEGY_CATEGORIES, "trend", warnings
    )
    version = _normalize_version(context.get("version"), warnings)
    author = _normalize_optional_str(context.get("author"))

    strategy_yaml = _render_strategy_yaml(
        strategy_id=strategy_id,
        name=name,
        version=version,
        author=author,
        category=category,
        warmup_bars=warmup_bars,
        series_inputs=series_inputs,
        indicators=indicators,
        params=params,
        provides_confidence=provides_confidence,
    )

    strategy_py = _render_strategy_py(provides_confidence)

    steps = [
        _step("create_dir", f"Create directory user_strategies/{strategy_id}/."),
        _step(
            "write_yaml",
            "Fill strategy.yaml with required fields (template below).",
        ),
        _step(
            "write_py",
            "Implement on_bar(ctx) in strategy.py (template below).",
        ),
        _step(
            "validate",
            "Run the validator: python -m src.plugins.validate --out artifacts/plugins",
        ),
        _step("test", "Run ruff and pytest to confirm it passes."),
    ]

    files = [
        {
            "path": f"user_strategies/{strategy_id}/strategy.yaml",
            "contents": strategy_yaml,
        },
        {
            "path": f"user_strategies/{strategy_id}/strategy.py",
            "contents": strategy_py,
        },
    ]

    commands = [
        "python -m src.plugins.validate --out artifacts/plugins",
        "python -m ruff check .",
        "python -m pytest",
    ]
    success = [
        f"user_strategies/{strategy_id}/strategy.yaml exists",
        f"user_strategies/{strategy_id}/strategy.py exists",
        f"artifacts/plugins/strategy/{strategy_id}/validation.json status=PASS",
        "Strategy appears in the UI Strategy dropdown (validated plugins only).",
    ]
    warnings.extend(
        [
            "Strategies are decision logic only; no execution, I/O, or randomness.",
            "Version bump required for any behavior change.",
        ]
    )

    diagnostics = _diagnostics(request, notes)
    return ChatResponse(
        mode="add_strategy",
        title=f"Add Strategy: {name}",
        summary="Template files and validation steps for a new strategy.",
        steps=steps,
        files_to_create=[FileTemplate(**item) for item in files],
        commands=commands,
        success_criteria=success,
        warnings=warnings,
        blockers=[],
        diagnostics=diagnostics,
    )


def _review_plugin(request: ChatRequest) -> ChatResponse:
    context = request.context or {}
    notes: list[str] = []
    warnings: list[str] = []
    blockers: list[str] = []

    kind = _pick_value(context, ["kind", "plugin_type", "type"], "").lower()
    plugin_id = _pick_value(context, ["id", "plugin_id", "indicator_id", "strategy_id"], "")
    path_optional = _pick_value(context, ["path_optional", "path"], "")

    if not kind or not plugin_id:
        return _fail_closed(
            request,
            "review_plugin",
            "insufficient artifacts for review",
            missing=["context.kind", "context.id"],
            steps=_review_missing_steps(kind=None, plugin_id=None),
            commands=_review_missing_commands(kind=None, plugin_id=None),
        )

    if kind not in {"indicator", "strategy"}:
        return _fail_closed(
            request,
            "review_plugin",
            "insufficient artifacts for review",
            missing=["context.kind"],
            steps=_review_missing_steps(kind=None, plugin_id=None),
            commands=_review_missing_commands(kind=None, plugin_id=None),
        )

    repo_root = _repo_root()
    plugin_dir, yaml_path, py_path = _resolve_plugin_paths(
        repo_root=repo_root,
        kind=kind,
        plugin_id=plugin_id,
        path_optional=path_optional,
        notes=notes,
    )
    if plugin_dir is None or yaml_path is None or py_path is None:
        return _fail_closed(
            request,
            "review_plugin",
            "insufficient artifacts for review",
            missing=["plugin_path"],
            steps=_review_missing_steps(kind=kind, plugin_id=plugin_id),
            commands=_review_missing_commands(kind=kind, plugin_id=plugin_id),
        )

    missing_files = [path for path in (yaml_path, py_path) if not path.exists()]
    if missing_files:
        missing = [str(path.as_posix()) for path in missing_files]
        return _fail_closed(
            request,
            "review_plugin",
            "insufficient artifacts for review",
            missing=missing,
            steps=_review_missing_steps(kind=kind, plugin_id=plugin_id),
            commands=_review_missing_commands(kind=kind, plugin_id=plugin_id),
        )

    yaml_payload, yaml_error = _load_yaml(yaml_path)
    if yaml_error:
        blockers.append(f"{yaml_path.name} invalid: {yaml_error}")
    elif yaml_payload is not None:
        schema_blockers, schema_warnings = _validate_schema(
            yaml_payload, kind, plugin_id=str(plugin_id)
        )
        blockers.extend(schema_blockers)
        warnings.extend(schema_warnings)

    py_source, py_tree, py_error = _load_python(py_path)
    if py_error:
        blockers.append(f"{py_path.name} invalid: {py_error}")
    elif py_tree is not None:
        blockers.extend(_validate_interface(py_tree, kind))
        blockers.extend(_scan_forbidden_imports(py_tree))
        warnings.extend(_scan_lookahead(py_source or ""))
        warnings.extend(_scan_non_determinism(py_source or ""))

    suggestions = _review_suggestions(kind)
    notes.extend(suggestions)

    summary = _review_summary(blockers, warnings)
    steps = [_step("review_summary", "Review completed against contract and safety rules.")]
    for idx, suggestion in enumerate(suggestions, start=1):
        steps.append(_step(f"suggestion_{idx}", suggestion))

    diagnostics = _diagnostics(request, notes)
    return ChatResponse(
        mode="review_plugin",
        title=f"Review {kind.title()}: {plugin_id}",
        summary=summary,
        steps=steps,
        files_to_create=[],
        commands=_review_commands(),
        success_criteria=["Resolve blockers and rerun validator until PASS."],
        warnings=warnings,
        blockers=blockers,
        diagnostics=diagnostics,
    )


def _explain_trade(request: ChatRequest) -> ChatResponse:
    context = request.context or {}
    notes: list[str] = []

    run_id = _pick_value(context, ["run_id"], "")
    trade_id = _pick_value(context, ["trade_id", "tradeId"], "")
    decision_id = _pick_value(context, ["decision_id", "decisionId"], "")

    if not run_id or (not trade_id and not decision_id):
        return _fail_closed(
            request,
            "explain_trade",
            "insufficient artifacts for trade explanation",
            missing=["context.run_id", "context.trade_id_or_decision_id"],
            steps=_explain_missing_steps(run_id),
            commands=_explain_missing_commands(run_id),
        )

    if not _is_valid_run_id(run_id):
        return _fail_closed_invalid_run_id(request, run_id)

    run_dir, root_used, invalid = _resolve_run_dir(run_id)
    if invalid:
        return _fail_closed_invalid_run_id(request, run_id)
    if run_dir is None or root_used is None:
        return _fail_closed(
            request,
            "explain_trade",
            "insufficient artifacts for trade explanation",
            missing=[f"run_dir:{run_id}"],
            steps=_explain_missing_steps(run_id),
            commands=_explain_missing_commands(run_id),
        )

    notes.append(f"artifacts_root={root_used.as_posix()}")

    decision_path = run_dir / "decision_records.jsonl"
    if not decision_path.exists():
        return _fail_closed(
            request,
            "explain_trade",
            "insufficient artifacts for trade explanation",
            missing=[decision_path.as_posix()],
            steps=_explain_missing_steps(run_id),
            commands=_explain_missing_commands(run_id),
        )

    trade_path = run_dir / "trades.parquet"
    if trade_id and not trade_path.exists():
        return _fail_closed(
            request,
            "explain_trade",
            "insufficient artifacts for trade explanation",
            missing=[trade_path.as_posix()],
            steps=_explain_missing_steps(run_id),
            commands=_explain_missing_commands(run_id),
        )

    decision_records = list(DecisionRecords(decision_path))
    steps: list[Step] = []
    warnings: list[str] = []
    blockers: list[str] = []

    trade_events: list[dict[str, Any]] = []
    trade_window = None
    if trade_id:
        trade_events = _load_trade_events(trade_path, trade_id)
        if not trade_events:
            blockers.append(f"trade_id_not_found:{trade_id}")
        else:
            trade_window = _trade_time_window(trade_events)
            summary = ", ".join(
                f"{event['timestamp']} {event['side']} @ {event['price']}" for event in trade_events
            )
            steps.append(_step("trade_events", f"Trade events: {summary}."))

    if decision_id:
        matching = _find_decision_by_id(decision_records, decision_id)
        if matching is None:
            blockers.append(f"decision_id_not_found:{decision_id}")
        else:
            steps.append(
                _step(
                    "decision_match",
                    "Decision record: "
                    f"{_record_timestamp(matching)} action={matching.get('action')}",
                )
            )

    if decision_records:
        near_decisions = _filter_decisions_by_window(decision_records, trade_window)
        if near_decisions:
            summary = ", ".join(
                f"{_record_timestamp(item)} {item.get('action')}" for item in near_decisions[:5]
            )
            steps.append(_step("nearby_decisions", f"Nearby decisions: {summary}."))
        else:
            warnings.append("No decision records found near the trade window.")

    strategy_id, symbols, timeframe = extract_run_metadata(decision_path)
    if strategy_id or symbols or timeframe:
        steps.append(
            _step(
                "run_context",
                "Run context: "
                f"strategy_id={strategy_id or 'n/a'}, "
                f"symbols={','.join(symbols or []) or 'n/a'}, "
                f"timeframe={timeframe or 'n/a'}.",
            )
        )

    params = _extract_params(decision_records)
    if params:
        steps.append(_step("strategy_params", f"Strategy params snapshot: {params}."))
    else:
        warnings.append("Strategy params not found in decision records.")

    timeline_path = find_timeline_path(run_dir)
    if timeline_path is not None:
        try:
            timeline = _load_timeline_events(timeline_path)
        except ValueError as exc:
            warnings.append(f"timeline invalid: {exc}")
        else:
            if timeline:
                steps.append(
                    _step(
                        "timeline",
                        "Timeline highlights: "
                        + ", ".join(
                            f"{event['timestamp']} {event['title']}" for event in timeline[:3]
                        )
                        + ".",
                    )
                )

    diagnostics = _diagnostics(request, notes)
    summary = "Trade explanation based on artifacts only."
    if blockers:
        summary = "Trade explanation incomplete due to missing identifiers."

    return ChatResponse(
        mode="explain_trade",
        title=f"Explain Trade: {trade_id or decision_id}",
        summary=summary,
        steps=steps,
        files_to_create=[],
        commands=[],
        success_criteria=["Explanation derived from available artifacts."],
        warnings=warnings,
        blockers=blockers,
        diagnostics=diagnostics,
    )


def _diagnostics(request: ChatRequest, notes: list[str]) -> Diagnostics:
    inputs = {
        "mode": request.mode,
        "message": request.message or "",
        "context": request.context or {},
    }
    return Diagnostics(inputs=inputs, notes=notes)


def _step(step_id: str, text: str) -> Step:
    return Step(id=step_id, text=text)


def _fail_closed(
    request: ChatRequest,
    mode: str,
    title: str,
    *,
    missing: list[str],
    steps: list[Step],
    commands: list[str],
) -> ChatResponse:
    diagnostics = _diagnostics(request, [f"missing={missing}"])
    blockers = ["insufficient_artifacts", *missing]
    return ChatResponse(
        mode=mode,
        title=title,
        summary="Required artifacts are missing. Follow the steps to generate them.",
        steps=steps,
        files_to_create=[],
        commands=commands,
        success_criteria=[],
        warnings=[],
        blockers=blockers,
        diagnostics=diagnostics,
    )


def _review_missing_steps(kind: str | None, plugin_id: str | None) -> list[Step]:
    steps: list[Step] = []
    for command, label in _review_template_commands(kind, plugin_id):
        steps.append(_step(label, f"Generate templates: {command}"))
    steps.extend(
        [
            _step("create_files", "Create indicator/strategy YAML and Python files."),
            _step(
                "validate",
                "Run: python -m src.plugins.validate --out artifacts/plugins",
            ),
        ]
    )
    return steps


def _review_commands() -> list[str]:
    return [
        "python -m src.plugins.validate --out artifacts/plugins",
        "python -m ruff check .",
        "python -m pytest",
    ]


def _review_missing_commands(kind: str | None, plugin_id: str | None) -> list[str]:
    commands = [command for command, _ in _review_template_commands(kind, plugin_id)]
    commands.extend(_review_commands())
    return commands


def _review_template_commands(
    kind: str | None,
    plugin_id: str | None,
) -> list[tuple[str, str]]:
    resolved_id = plugin_id or "<plugin_id>"
    commands: list[tuple[str, str]] = []
    if kind in {None, "indicator"}:
        commands.append(
            (
                _build_template_command(
                    mode="add_indicator",
                    id_key="indicator_id",
                    plugin_id=resolved_id,
                ),
                "generate_indicator_templates",
            )
        )
    if kind in {None, "strategy"}:
        commands.append(
            (
                _build_template_command(
                    mode="add_strategy",
                    id_key="strategy_id",
                    plugin_id=resolved_id,
                ),
                "generate_strategy_templates",
            )
        )
    return commands


def _build_template_command(*, mode: str, id_key: str, plugin_id: str) -> str:
    payload = {"mode": mode, "message": "generate", "context": {id_key: plugin_id}}
    payload_json = json.dumps(payload)
    return (
        "python -c "
        '"import json, urllib.request; '
        f"payload=json.loads('{payload_json}'); "
        "req=urllib.request.Request("
        "'http://127.0.0.1:8000/api/v1/chat', "
        "data=json.dumps(payload).encode(), "
        "headers={'Content-Type':'application/json'}); "
        'print(urllib.request.urlopen(req).read().decode())"'
    )


def _explain_missing_steps(run_id: str) -> list[Step]:
    run_label = run_id or "<run_id>"
    return [
        _step(
            "generate_artifacts",
            "Generate decision_records.jsonl and trades.parquet for the run.",
        ),
        _step(
            "backtest_command",
            'Example backtest command: python -c "import pandas as pd; '
            "from src.backtest.harness import run_backtest; "
            f"df=pd.read_parquet('<path_to_ohlcv.parquet>'); "
            f"run_backtest(df, initial_equity=10000, run_id='{run_label}', "
            "out_dir='artifacts')\"",
        ),
        _step(
            "set_root",
            "Ensure ARTIFACTS_ROOT points to the artifacts directory if using a custom path.",
        ),
    ]


def _explain_missing_commands(run_id: str) -> list[str]:
    run_label = run_id or "<run_id>"
    return [
        "python -c "
        '"import pandas as pd; from src.backtest.harness import run_backtest; '
        f"df=pd.read_parquet('<path_to_ohlcv.parquet>'); "
        f"run_backtest(df, initial_equity=10000, run_id='{run_label}', "
        "out_dir='artifacts')\"",
    ]


def _resolve_run_dir(run_id: str) -> tuple[Path | None, Path | None, bool]:
    candidates = [get_artifacts_root(), Path("runs"), Path("workspaces")]
    root_used: Path | None = None
    for root in candidates:
        root_used = root.expanduser().resolve()
        candidate = (root_used / run_id).resolve()
        if not _is_within_root(candidate, root_used):
            return None, root_used, True
        if candidate.exists() and candidate.is_dir():
            return candidate, root_used, False
    return None, root_used, False


def _is_valid_run_id(run_id: str) -> bool:
    candidate_id = (run_id or "").strip()
    if not candidate_id:
        return False
    if Path(candidate_id).is_absolute():
        return False
    if ".." in candidate_id:
        return False
    if "/" in candidate_id or "\\" in candidate_id:
        return False
    if not _RUN_ID_RE.match(candidate_id):
        return False
    return True


def _fail_closed_invalid_run_id(request: ChatRequest, run_id: str) -> ChatResponse:
    diagnostics = _diagnostics(request, [f"invalid_run_id={run_id}"])
    steps = [
        _step("invalid_run_id", "Provide a valid run_id (letters, numbers, ._- only)."),
        *_explain_missing_steps(run_id),
    ]
    return ChatResponse(
        mode="explain_trade",
        title="invalid run id",
        summary="The provided run_id is invalid; no artifacts were read.",
        steps=steps,
        files_to_create=[],
        commands=_explain_missing_commands(run_id),
        success_criteria=[],
        warnings=[],
        blockers=["invalid_run_id"],
        diagnostics=diagnostics,
    )


def _resolve_plugin_paths(
    *,
    repo_root: Path,
    kind: str,
    plugin_id: str,
    path_optional: str,
    notes: list[str],
) -> tuple[Path | None, Path | None, Path | None]:
    base_dir: Path
    if path_optional:
        candidate = Path(path_optional)
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        candidate = candidate.resolve()
        if not _is_within_repo(candidate, repo_root):
            notes.append("path_optional outside repo root; ignoring.")
            return None, None, None
        if candidate.is_file():
            base_dir = candidate.parent
        else:
            base_dir = candidate
    else:
        base_dir = (
            repo_root
            / ("user_indicators" if kind == "indicator" else "user_strategies")
            / plugin_id
        )

    yaml_name = "indicator.yaml" if kind == "indicator" else "strategy.yaml"
    py_name = "indicator.py" if kind == "indicator" else "strategy.py"
    return base_dir, base_dir / yaml_name, base_dir / py_name


def _render_indicator_yaml(
    *,
    indicator_id: str,
    name: str,
    version: str,
    author: str | None,
    category: str,
    inputs: list[str],
    outputs: list[str],
    params: list[dict[str, Any]],
    warmup_bars: int,
    nan_policy: str,
) -> str:
    author_line = f"author: {author}" if author else "author: TODO"
    params_yaml = _render_params_yaml(params)
    inputs_yaml = "\n".join([f"  - {item}" for item in inputs])
    outputs_yaml = "\n".join([f"  - {item}" for item in outputs])
    return "\n".join(
        [
            f"id: {indicator_id}",
            f"name: {name}",
            f"version: {version}",
            author_line,
            f"category: {category}",
            "inputs:",
            inputs_yaml or "  - close",
            "outputs:",
            outputs_yaml or "  - value",
            "params:",
            params_yaml,
            f"warmup_bars: {warmup_bars}",
            f"nan_policy: {nan_policy}",
            "",
        ]
    )


def _render_strategy_yaml(
    *,
    strategy_id: str,
    name: str,
    version: str,
    author: str | None,
    category: str,
    warmup_bars: int,
    series_inputs: list[str],
    indicators: list[str],
    params: list[dict[str, Any]],
    provides_confidence: bool,
) -> str:
    author_line = f"author: {author}" if author else "author: TODO"
    series_yaml = "\n".join([f"    - {item}" for item in series_inputs])
    indicators_yaml = "\n".join([f"    - {item}" for item in indicators]) or "    -"
    params_yaml = _render_params_yaml(params, indent=2)
    provides_text = "true" if provides_confidence else "false"
    return "\n".join(
        [
            f"id: {strategy_id}",
            f"name: {name}",
            f"version: {version}",
            author_line,
            f"category: {category}",
            f"warmup_bars: {warmup_bars}",
            "inputs:",
            "  series:",
            series_yaml or "    - close",
            "  indicators:",
            indicators_yaml,
            "params:",
            params_yaml,
            "outputs:",
            "  intents:",
            "    - HOLD",
            "    - ENTER_LONG",
            "    - ENTER_SHORT",
            "    - EXIT_LONG",
            "    - EXIT_SHORT",
            f"  provides_confidence: {provides_text}",
            "",
        ]
    )


def _render_params_yaml(params: list[dict[str, Any]], indent: int = 0) -> str:
    pad = " " * indent
    lines: list[str] = []
    for entry in params:
        description = json.dumps(str(entry.get("description", "")))
        lines.extend(
            [
                f"{pad}- name: {entry.get('name')}",
                f"{pad}  type: {entry.get('type')}",
                f"{pad}  default: {entry.get('default')}",
                f"{pad}  min: {entry.get('min')}",
                f"{pad}  max: {entry.get('max')}",
                f"{pad}  step: {entry.get('step')}",
                f"{pad}  description: {description}",
            ]
        )
    return "\n".join(lines) if lines else f"{pad}- name: TODO"


def _render_indicator_py(outputs: list[str]) -> str:
    output_lines = ", ".join(f'"{name}": value' for name in outputs) or '"value": 0.0'
    return "\n".join(
        [
            "def get_schema():",
            "    return {}",
            "",
            "",
            "def compute(ctx):",
            "    # TODO: implement indicator computation using ctx inputs only.",
            "    value = 0.0",
            f"    return {{{output_lines}}}",
            "",
        ]
    )


def _render_strategy_py(provides_confidence: bool) -> str:
    lines = [
        "def get_schema():",
        "    return {}",
        "",
        "",
        "def on_bar(ctx):",
        "    # TODO: implement entry/exit rules using ctx series and indicators.",
        '    decision = {"intent": "HOLD"}',
    ]
    if provides_confidence:
        lines.append('    decision["confidence"] = 0.0')
    lines.extend(["    return decision", ""])
    return "\n".join(lines)


def _normalize_id(value: str, fallback: str) -> tuple[str, str | None]:
    raw = str(value or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    if not slug:
        return fallback, None
    if not slug[0].isalpha():
        slug = f"{fallback}_{slug}"
    if not _ID_RE.match(slug):
        return fallback, "Invalid id format; using fallback id."
    return slug, None


def _normalize_string_list(value: Any, default: list[str]) -> list[str]:
    if value is None:
        return default
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",") if item.strip()]
        return items or default
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value or default
    return default


def _normalize_params(
    value: Any,
    default_name: str = "length",
    default_type: str = "int",
) -> list[dict[str, Any]]:
    if isinstance(value, list) and value:
        valid: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            param_type = item.get("type")
            if not isinstance(name, str) or not isinstance(param_type, str):
                continue
            if "default" not in item:
                continue
            entry = dict(item)
            entry.setdefault("min", 2 if default_type == "int" else -1.0)
            entry.setdefault("max", 200 if default_type == "int" else 1.0)
            entry.setdefault("step", 1 if default_type == "int" else 0.1)
            entry.setdefault("description", "TODO: describe parameter.")
            valid.append(entry)
        if valid:
            return valid
    return [
        {
            "name": default_name,
            "type": default_type,
            "default": 14 if default_type == "int" else 0.0,
            "min": 2 if default_type == "int" else -1.0,
            "max": 200 if default_type == "int" else 1.0,
            "step": 1 if default_type == "int" else 0.1,
            "description": "TODO: describe parameter.",
        }
    ]


def _normalize_int(value: Any, fallback: int) -> int:
    try:
        num = int(value)
    except (TypeError, ValueError):
        return int(fallback)
    return num if num >= 0 else int(fallback)


def _normalize_nan_policy(value: Any, warnings: list[str]) -> str:
    if isinstance(value, str) and value in _ALLOWED_NAN_POLICIES:
        return value
    if value:
        warnings.append("nan_policy invalid; using propagate.")
    return "propagate"


def _normalize_category(
    value: Any,
    allowed: set[str],
    fallback: str,
    warnings: list[str],
) -> str:
    if isinstance(value, str) and value in allowed:
        return value
    if value:
        warnings.append("category invalid; using fallback.")
    return fallback


def _normalize_version(value: Any, warnings: list[str]) -> str:
    if isinstance(value, str) and re.match(r"^\d+\.\d+\.\d+$", value):
        return value
    if value:
        warnings.append("version invalid; using 1.0.0.")
    return "1.0.0"


def _normalize_optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _pick_value(context: dict[str, Any], keys: list[str], fallback: str) -> str:
    for key in keys:
        if key in context and context[key] not in (None, ""):
            return str(context[key])
    return fallback


def _load_yaml(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, str(exc)
    if not isinstance(payload, dict):
        return None, "YAML must be a mapping."
    return payload, None


def _load_python(path: Path) -> tuple[str | None, ast.AST | None, str | None]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, None, str(exc)
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return source, None, exc.msg
    return source, tree, None


def _validate_schema(
    payload: dict[str, Any],
    kind: str,
    plugin_id: str,
) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []

    if kind == "indicator":
        required = [
            "id",
            "name",
            "version",
            "category",
            "inputs",
            "outputs",
            "params",
            "warmup_bars",
            "nan_policy",
        ]
    else:
        required = [
            "id",
            "name",
            "version",
            "category",
            "warmup_bars",
            "inputs",
            "params",
            "outputs",
        ]

    for key in required:
        if key not in payload:
            blockers.append(f"missing_field:{key}")

    schema_id = payload.get("id")
    if isinstance(schema_id, str):
        if not _ID_RE.match(schema_id):
            blockers.append("invalid_id_format")
        if schema_id != plugin_id:
            blockers.append("id_directory_mismatch")
    else:
        blockers.append("invalid_id_type")

    category = payload.get("category")
    allowed = _ALLOWED_INDICATOR_CATEGORIES if kind == "indicator" else _ALLOWED_STRATEGY_CATEGORIES
    if isinstance(category, str) and category not in allowed:
        blockers.append("invalid_category")

    inputs = payload.get("inputs")
    if kind == "indicator":
        if not isinstance(inputs, list):
            blockers.append("indicator_inputs_invalid")
    else:
        if not isinstance(inputs, dict):
            blockers.append("strategy_inputs_invalid")
        else:
            if not isinstance(inputs.get("series"), list):
                blockers.append("strategy_inputs_series_invalid")
            if not isinstance(inputs.get("indicators"), list):
                blockers.append("strategy_inputs_indicators_invalid")

    outputs = payload.get("outputs")
    if kind == "indicator":
        if not isinstance(outputs, list):
            blockers.append("indicator_outputs_invalid")
    else:
        if not isinstance(outputs, dict):
            blockers.append("strategy_outputs_invalid")
        else:
            intents = outputs.get("intents")
            if not isinstance(intents, list):
                blockers.append("strategy_intents_invalid")
            else:
                invalid = [intent for intent in intents if intent not in _ALLOWED_INTENTS]
                if invalid:
                    blockers.append("strategy_intents_invalid_values")
            if not isinstance(outputs.get("provides_confidence"), bool):
                blockers.append("strategy_confidence_invalid")

    params = payload.get("params")
    if not isinstance(params, list):
        blockers.append("params_invalid")
    elif not params:
        warnings.append("params_empty")

    nan_policy = payload.get("nan_policy")
    if kind == "indicator" and isinstance(nan_policy, str):
        if nan_policy not in _ALLOWED_NAN_POLICIES:
            blockers.append("nan_policy_invalid")
        if nan_policy == "fill":
            warnings.append("nan_policy_fill_discouraged")

    warmup_bars = payload.get("warmup_bars")
    if isinstance(warmup_bars, int) and warmup_bars == 0:
        warnings.append("warmup_bars_zero")

    return blockers, warnings


def _validate_interface(tree: ast.AST, kind: str) -> list[str]:
    defs = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    missing: list[str] = []
    if "get_schema" not in defs:
        missing.append("missing_get_schema")
    if kind == "indicator":
        if "compute" not in defs:
            missing.append("missing_compute")
    else:
        if "on_bar" not in defs:
            missing.append("missing_on_bar")
    return missing


def _scan_forbidden_imports(tree: ast.AST) -> list[str]:
    blockers: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _FORBIDDEN_IMPORT_ROOTS:
                    blockers.append(f"forbidden_import:{alias.name}")
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".")[0]
            if root in _FORBIDDEN_IMPORT_ROOTS:
                blockers.append(f"forbidden_import:{module}")
    return blockers


def _scan_lookahead(source: str) -> list[str]:
    warnings: list[str] = []
    for pattern in ("shift(-", "iloc[-", "[-1]", ".shift(-"):
        if pattern in source:
            warnings.append("potential_lookahead_detected")
            break
    return warnings


def _scan_non_determinism(source: str) -> list[str]:
    warnings: list[str] = []
    for token in ("datetime.now", "datetime.utcnow", "time.time", "random"):
        if token in source:
            warnings.append("potential_non_determinism_detected")
            break
    return warnings


def _review_suggestions(kind: str) -> list[str]:
    if kind == "indicator":
        return [
            "Suggestion: add a unit test for warmup_bars and NaN policy behavior.",
            "Suggestion: add a test asserting output keys match indicator.yaml outputs.",
        ]
    return [
        "Suggestion: add tests for entry/exit intents under edge-case inputs.",
        "Suggestion: add a test ensuring on_bar returns valid intent values.",
    ]


def _review_summary(blockers: list[str], warnings: list[str]) -> str:
    return f"Review complete: blockers={len(blockers)}, warnings={len(warnings)}."


def _load_trade_events(trade_path: Path, trade_id: str) -> list[dict[str, Any]]:
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - env issue
        raise RuntimeError("pandas is required to read trades.parquet") from exc

    df = pd.read_parquet(trade_path)
    if df.empty:
        return []

    trade_col = None
    for candidate in ("trade_id", "tradeId", "id"):
        if candidate in df.columns:
            trade_col = candidate
            break
    if trade_col is None:
        return []

    df = df[df[trade_col].astype(str) == str(trade_id)]
    if df.empty:
        return []

    timestamp_col = _pick_timestamp_column(df.columns)
    events: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        timestamp = row.get(timestamp_col) if timestamp_col else None
        if timestamp is not None:
            try:
                ts = format_ts(parse_ts(timestamp))
            except ValueError:
                ts = None
        else:
            ts = None
        events.append(
            {
                "timestamp": ts or "n/a",
                "side": row.get("side") or row.get("direction") or row.get("action") or "n/a",
                "price": row.get("price"),
                "pnl": row.get("pnl"),
            }
        )
    return events


def _trade_time_window(events: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    timestamps = []
    for event in events:
        try:
            ts = parse_ts(event.get("timestamp"))
        except ValueError:
            continue
        if ts is not None:
            timestamps.append(ts)
    if not timestamps:
        return None, None
    timestamps.sort()
    return format_ts(timestamps[0]), format_ts(timestamps[-1])


def _filter_decisions_by_window(
    records: list[dict[str, Any]],
    window: tuple[str | None, str | None] | None,
) -> list[dict[str, Any]]:
    if not window or (window[0] is None and window[1] is None):
        return records[:5]
    start_ts = parse_ts(window[0]) if window[0] else None
    end_ts = parse_ts(window[1]) if window[1] else None
    results = []
    for record in records:
        ts_value = _record_timestamp(record)
        try:
            ts = parse_ts(ts_value)
        except ValueError:
            continue
        if start_ts and ts < start_ts:
            continue
        if end_ts and ts > end_ts:
            continue
        results.append(record)
    return results


def _record_timestamp(record: dict[str, Any]) -> Any:
    for key in _TIMESTAMP_FIELDS:
        if key in record:
            return record.get(key)
    metadata = record.get("metadata")
    if isinstance(metadata, dict):
        for key in _TIMESTAMP_FIELDS:
            if key in metadata:
                return metadata.get(key)
    return None


def _pick_timestamp_column(columns: Any) -> str | None:
    for name in _TIMESTAMP_FIELDS:
        if name in columns:
            return name
    return None


def _find_decision_by_id(records: list[dict[str, Any]], decision_id: str) -> dict[str, Any] | None:
    for record in records:
        for key in ("decision_id", "decisionId", "id"):
            if str(record.get(key, "")) == str(decision_id):
                return record
    return None


def _extract_params(records: list[dict[str, Any]]) -> str | None:
    for record in records:
        for key in ("params", "strategy_params", "parameters"):
            value = record.get(key)
            if isinstance(value, dict):
                return ", ".join(f"{k}={value[k]}" for k in sorted(value.keys()))
    return None


def _load_timeline_events(path: Path) -> list[dict[str, Any]]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(payload, list):
        raise ValueError("timeline must be a list")
    events = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        timestamp = item.get("timestamp") or item.get("ts_utc") or "n/a"
        title = item.get("title") or item.get("type") or "event"
        events.append({"timestamp": timestamp, "title": title})
    return events


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _is_within_repo(candidate: Path, repo_root: Path) -> bool:
    try:
        return candidate.resolve().is_relative_to(repo_root.resolve())
    except AttributeError:
        return repo_root.resolve() in candidate.resolve().parents


def _is_within_root(candidate: Path, root: Path) -> bool:
    try:
        return candidate.resolve().is_relative_to(root.resolve())
    except AttributeError:
        resolved = candidate.resolve()
        root_resolved = root.resolve()
        return resolved == root_resolved or root_resolved in resolved.parents


def _empty_response(mode: str, title: str) -> ChatResponse:
    diagnostics = Diagnostics(inputs={"mode": mode}, notes=[])
    return ChatResponse(
        mode=mode,
        title=title,
        summary="",
        steps=[],
        files_to_create=[],
        commands=[],
        success_criteria=[],
        warnings=[],
        blockers=[],
        diagnostics=diagnostics,
    )
