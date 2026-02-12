from __future__ import annotations

import ast
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Literal

import yaml

from .discovery import PluginCandidate, PluginType

ValidationStatus = Literal["VALID", "INVALID"]

ALLOWED_INDICATOR_CATEGORIES = {
    "trend",
    "momentum",
    "volatility",
    "volume",
    "statistics",
    "structure",
}
ALLOWED_STRATEGY_CATEGORIES = {
    "trend",
    "mr",
    "momentum",
    "volatility",
    "structure",
    "wrapper",
}
ALLOWED_INTENTS = {
    "HOLD",
    "ENTER_LONG",
    "ENTER_SHORT",
    "EXIT_LONG",
    "EXIT_SHORT",
}
ALLOWED_NAN_POLICIES = {"propagate", "fill", "error"}
ALLOWED_PARAM_TYPES = {"int", "float", "bool", "string", "str", "enum"}

INDICATOR_ALLOWED_KEYS = {
    "id",
    "name",
    "version",
    "author",
    "category",
    "inputs",
    "outputs",
    "params",
    "warmup_bars",
    "nan_policy",
}
STRATEGY_ALLOWED_KEYS = {
    "id",
    "name",
    "version",
    "author",
    "category",
    "warmup_bars",
    "inputs",
    "params",
    "outputs",
    "nan_policy",
}

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")

MAX_PLUGIN_SOURCE_BYTES = 200_000
MAX_PLUGIN_AST_NODES = 20_000


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    plugin_id: str
    plugin_type: PluginType
    name: str | None
    version: str | None
    category: str | None
    status: ValidationStatus
    issues: list[ValidationIssue]
    checked_at_utc: str
    source_hash: str
    warnings: list[str]

    @property
    def reason_codes(self) -> list[str]:
        return [issue.code for issue in self.issues]

    @property
    def reason_messages(self) -> list[str]:
        return [issue.message for issue in self.issues]


def validate_all(candidates: Iterable[PluginCandidate], out_dir: Path) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    for candidate in candidates:
        result = validate_candidate(candidate)
        if result.warnings:
            for warning in result.warnings:
                print(f"warning:{result.plugin_type}/{result.plugin_id}: {warning}")
        result = _write_result_with_fail_closed(result, out_dir)
        results.append(result)

    write_validation_index(results, out_dir)
    return results


def validate_candidate(candidate: PluginCandidate) -> ValidationResult:
    try:
        return _validate_candidate(candidate)
    except Exception as exc:  # pragma: no cover - hard fail-closed guard.
        issues = [
            ValidationIssue(
                code="VALIDATION_EXCEPTION",
                message=f"Validator crashed: {exc}",
            )
        ]
        source_hash = _hash_plugin_dir(candidate.plugin_dir, issues)
        return _result(candidate, issues, _empty_meta(), source_hash=source_hash)


def write_validation_artifact(result: ValidationResult, out_dir: Path) -> None:
    out_root = Path(out_dir)
    dest = out_root / result.plugin_type / f"{result.plugin_id}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = _build_record_payload(result)
    _atomic_write_json(dest, payload)


def write_validation_index(results: Iterable[ValidationResult], out_dir: Path) -> None:
    payload = _build_index_payload(results)
    out_root = Path(out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    dest = out_root / "index.json"
    _atomic_write_json(dest, payload)


def _write_result_with_fail_closed(
    result: ValidationResult, out_dir: Path
) -> ValidationResult:
    try:
        write_validation_artifact(result, out_dir)
        return result
    except Exception as exc:  # pragma: no cover - filesystem failures
        issues = list(result.issues)
        _add_issue(
            issues,
            "ARTIFACT_WRITE_ERROR",
            f"Failed to write validation artifact: {exc}",
        )
        fallback = _result(
            _candidate_from_result(result),
            issues,
            _meta_from_result(result),
            source_hash=result.source_hash,
        )
        try:
            write_validation_artifact(fallback, out_dir)
        except Exception:
            pass
        return fallback


def _candidate_from_result(result: ValidationResult) -> PluginCandidate:
    return PluginCandidate(
        plugin_id=result.plugin_id,
        plugin_type=result.plugin_type,
        plugin_dir=Path("."),
        yaml_path=Path(""),
        py_path=Path(""),
        extra_files=[],
    )


def _meta_from_result(result: ValidationResult) -> dict[str, str | None]:
    return {
        "name": result.name,
        "version": result.version,
        "category": result.category,
    }


def _build_record_payload(result: ValidationResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "plugin_type": result.plugin_type,
        "id": result.plugin_id,
        "status": result.status,
        "reason_codes": result.reason_codes,
        "reason_messages": result.reason_messages,
        "checked_at_utc": result.checked_at_utc,
        "source_hash": result.source_hash,
    }
    if result.name:
        payload["name"] = result.name
    if result.version:
        payload["version"] = result.version
    if result.category:
        payload["category"] = result.category
    return payload


def _build_index_payload(results: Iterable[ValidationResult]) -> dict[str, Any]:
    plugins: dict[str, dict[str, Any]] = {}
    total_valid = 0
    total_invalid = 0
    for result in sorted(results, key=lambda item: (item.plugin_type, item.plugin_id)):
        key = f"{result.plugin_type}:{result.plugin_id}"
        plugins[key] = {
            "id": result.plugin_id,
            "plugin_type": result.plugin_type,
            "status": result.status,
            "source_hash": result.source_hash,
            "checked_at_utc": result.checked_at_utc,
            "name": result.name,
            "version": result.version,
            "category": result.category,
        }
        if result.status == "VALID":
            total_valid += 1
        else:
            total_invalid += 1

    payload = {
        "index_built_at": _utc_now_iso(),
        "total_plugins": len(plugins),
        "total_valid": total_valid,
        "total_invalid": total_invalid,
        "plugins": plugins,
    }
    payload["content_hash"] = _compute_index_content_hash(payload)
    return payload


def _compute_index_content_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        {
            "total_plugins": payload.get("total_plugins"),
            "total_valid": payload.get("total_valid"),
            "total_invalid": payload.get("total_invalid"),
            "plugins": payload.get("plugins"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(payload, indent=2, sort_keys=True)
    try:
        tmp_path.write_text(data, encoding="utf-8")
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise

def _validate_candidate(candidate: PluginCandidate) -> ValidationResult:
    issues: list[ValidationIssue] = []
    warnings: list[str] = []

    if candidate.extra_files:
        warnings.append(
            "Unexpected top-level files: " + ", ".join(sorted(candidate.extra_files))
        )

    source_hash = _hash_plugin_dir(candidate.plugin_dir, issues)

    yaml_payload = _load_yaml(candidate.yaml_path, issues)
    meta = _empty_meta()
    if yaml_payload is not None:
        meta = _extract_meta(yaml_payload)
        _ensure_no_callables(yaml_payload, "root", issues)
        if candidate.plugin_type == "indicator":
            _validate_indicator_schema(candidate, yaml_payload, issues)
        else:
            _validate_strategy_schema(candidate, yaml_payload, issues)

    _source, py_tree = _load_python(candidate.py_path, issues)
    if py_tree is not None:
        _validate_interface(candidate, py_tree, issues)
        _validate_global_state(py_tree, issues)
        _validate_static_safety(py_tree, issues)

    return _result(candidate, issues, meta, source_hash, warnings)


def _result(
    candidate: PluginCandidate,
    issues: list[ValidationIssue],
    meta: dict[str, str | None],
    source_hash: str,
    warnings: list[str] | None = None,
) -> ValidationResult:
    status: ValidationStatus = "VALID" if not issues else "INVALID"
    return ValidationResult(
        plugin_id=candidate.plugin_id,
        plugin_type=candidate.plugin_type,
        name=meta.get("name"),
        version=meta.get("version"),
        category=meta.get("category"),
        status=status,
        issues=issues,
        checked_at_utc=_utc_now_iso(),
        source_hash=source_hash,
        warnings=warnings or [],
    )


def _load_yaml(path: Path, issues: list[ValidationIssue]) -> dict[str, Any] | None:
    if not path.exists():
        _add_issue(issues, f"MISSING_FILE:{path.name}", f"{path.name} is missing.")
        return None
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        _add_issue(issues, "YAML_PARSE_ERROR", f"Failed to read {path.name}: {exc}")
        return None
    try:
        payload = yaml.safe_load(raw)
    except Exception as exc:
        _add_issue(issues, "YAML_PARSE_ERROR", f"Failed to parse {path.name}: {exc}")
        return None
    if not isinstance(payload, dict):
        _add_issue(issues, "INVALID_TYPE:root", f"{path.name} must be a mapping.")
        return None
    return payload


def _load_python(path: Path, issues: list[ValidationIssue]) -> tuple[str | None, ast.AST | None]:
    if not path.exists():
        _add_issue(issues, f"MISSING_FILE:{path.name}", f"{path.name} is missing.")
        return None, None
    try:
        if path.stat().st_size > MAX_PLUGIN_SOURCE_BYTES:
            _add_issue(
                issues,
                "TOO_LARGE",
                f"{path.name} exceeds the maximum size of {MAX_PLUGIN_SOURCE_BYTES} bytes.",
            )
            return None, None
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        _add_issue(issues, "AST_PARSE_ERROR", f"Failed to read {path.name}: {exc}")
        return None, None
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        _add_issue(issues, "AST_PARSE_ERROR", f"{path.name} syntax error: {exc.msg}")
        return source, None
    node_count = sum(1 for _ in ast.walk(tree))
    if node_count > MAX_PLUGIN_AST_NODES:
        _add_issue(
            issues,
            "TOO_LARGE",
            f"{path.name} exceeds the AST node limit of {MAX_PLUGIN_AST_NODES}.",
        )
        return source, None
    return source, tree


def _validate_indicator_schema(
    candidate: PluginCandidate,
    payload: dict[str, Any],
    issues: list[ValidationIssue],
) -> None:
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
    _require_fields(payload, required, issues)
    _reject_unknown_fields(payload, INDICATOR_ALLOWED_KEYS, issues)
    _validate_common_schema(candidate, payload, issues, ALLOWED_INDICATOR_CATEGORIES)

    inputs = payload.get("inputs")
    if inputs is not None:
        _validate_string_list(inputs, "inputs", issues)

    outputs = payload.get("outputs")
    if outputs is not None:
        _validate_string_list(outputs, "outputs", issues)

    params = payload.get("params")
    if params is not None:
        _validate_params(params, "params", issues)

    nan_policy = payload.get("nan_policy")
    if nan_policy is not None and nan_policy not in ALLOWED_NAN_POLICIES:
        _add_issue(
            issues,
            "INVALID_ENUM:nan_policy",
            "indicator.yaml nan_policy must be one of propagate, fill, error.",
        )


def _validate_strategy_schema(
    candidate: PluginCandidate,
    payload: dict[str, Any],
    issues: list[ValidationIssue],
) -> None:
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
    _require_fields(payload, required, issues)
    _reject_unknown_fields(payload, STRATEGY_ALLOWED_KEYS, issues)
    _validate_common_schema(candidate, payload, issues, ALLOWED_STRATEGY_CATEGORIES)

    inputs = payload.get("inputs")
    if inputs is not None:
        if not isinstance(inputs, dict):
            _add_issue(issues, "INVALID_TYPE:inputs", "strategy.yaml inputs must be a mapping.")
        else:
            if "series" not in inputs:
                _add_issue(
                    issues,
                    "SCHEMA_MISSING_FIELD:inputs.series",
                    "strategy.yaml inputs.series is required.",
                )
            else:
                _validate_string_list(inputs.get("series"), "inputs.series", issues)
            if "indicators" not in inputs:
                _add_issue(
                    issues,
                    "SCHEMA_MISSING_FIELD:inputs.indicators",
                    "strategy.yaml inputs.indicators is required.",
                )
            else:
                _validate_string_list(
                    inputs.get("indicators"), "inputs.indicators", issues
                )

    outputs = payload.get("outputs")
    if outputs is not None:
        if not isinstance(outputs, dict):
            _add_issue(
                issues, "INVALID_TYPE:outputs", "strategy.yaml outputs must be a mapping."
            )
        else:
            if "intents" not in outputs:
                _add_issue(
                    issues,
                    "SCHEMA_MISSING_FIELD:outputs.intents",
                    "strategy.yaml outputs.intents is required.",
                )
            else:
                intents = outputs.get("intents")
                _validate_string_list(intents, "outputs.intents", issues)
                if isinstance(intents, list):
                    invalid = [intent for intent in intents if intent not in ALLOWED_INTENTS]
                    if invalid:
                        _add_issue(
                            issues,
                            "INVALID_ENUM:outputs.intents",
                            f"strategy.yaml intents contain invalid values: {sorted(invalid)}.",
                        )
            if "provides_confidence" not in outputs:
                _add_issue(
                    issues,
                    "SCHEMA_MISSING_FIELD:outputs.provides_confidence",
                    "strategy.yaml outputs.provides_confidence is required.",
                )
            else:
                provides_confidence = outputs.get("provides_confidence")
                if provides_confidence is not None and not isinstance(provides_confidence, bool):
                    _add_issue(
                        issues,
                        "INVALID_TYPE:outputs.provides_confidence",
                        "strategy.yaml outputs.provides_confidence must be a boolean.",
                    )

    params = payload.get("params")
    if params is not None:
        _validate_params(params, "params", issues)

    nan_policy = payload.get("nan_policy")
    if nan_policy is not None and nan_policy not in ALLOWED_NAN_POLICIES:
        _add_issue(
            issues,
            "INVALID_ENUM:nan_policy",
            "strategy.yaml nan_policy must be one of propagate, fill, error.",
        )


def _validate_common_schema(
    candidate: PluginCandidate,
    payload: dict[str, Any],
    issues: list[ValidationIssue],
    allowed_categories: set[str],
) -> None:
    plugin_id = payload.get("id")
    if isinstance(plugin_id, str):
        if not plugin_id:
            _add_issue(issues, "INVALID_ENUM:id", "Schema id must be non-empty.")
        elif not ID_RE.match(plugin_id):
            _add_issue(
                issues,
                "INVALID_ENUM:id",
                "Schema id must be snake_case (lowercase letters, numbers, underscores).",
            )
        if plugin_id != candidate.plugin_id:
            _add_issue(
                issues,
                "INVALID_ENUM:id",
                f"Schema id '{plugin_id}' does not match directory '{candidate.plugin_id}'.",
            )
    else:
        _add_issue(issues, "INVALID_TYPE:id", "Schema id must be a string.")

    name = payload.get("name")
    if name is not None and not isinstance(name, str):
        _add_issue(issues, "INVALID_TYPE:name", "Schema name must be a string.")

    version = payload.get("version")
    if isinstance(version, str):
        if not SEMVER_RE.match(version):
            _add_issue(issues, "INVALID_ENUM:version", "Schema version must be semver (x.y.z).")
    else:
        _add_issue(issues, "INVALID_TYPE:version", "Schema version must be a string.")

    category = payload.get("category")
    if isinstance(category, str):
        if category not in allowed_categories:
            _add_issue(
                issues,
                "INVALID_ENUM:category",
                f"Schema category '{category}' is not allowed.",
            )
    else:
        _add_issue(issues, "INVALID_TYPE:category", "Schema category must be a string.")

    warmup_bars = payload.get("warmup_bars")
    if not isinstance(warmup_bars, int):
        _add_issue(issues, "INVALID_TYPE:warmup_bars", "warmup_bars must be an integer.")
    elif warmup_bars < 0:
        _add_issue(issues, "INVALID_ENUM:warmup_bars", "warmup_bars must be >= 0.")

def _validate_params(params: Any, field: str, issues: list[ValidationIssue]) -> None:
    if not isinstance(params, list):
        _add_issue(issues, f"INVALID_TYPE:{field}", "params must be a list.")
        return
    for idx, param in enumerate(params):
        path = f"{field}[{idx}]"
        if not isinstance(param, dict):
            _add_issue(
                issues,
                f"INVALID_TYPE:{path}",
                f"params[{idx}] must be a mapping.",
            )
            continue

        name = param.get("name")
        if not isinstance(name, str) or not name:
            _add_issue(
                issues,
                f"SCHEMA_MISSING_FIELD:{path}.name",
                f"params[{idx}] missing name.",
            )

        param_type = param.get("type")
        if not isinstance(param_type, str) or not param_type:
            _add_issue(
                issues,
                f"SCHEMA_MISSING_FIELD:{path}.type",
                f"params[{idx}] missing type.",
            )
        elif param_type not in ALLOWED_PARAM_TYPES:
            _add_issue(
                issues,
                f"INVALID_ENUM:{path}.type",
                f"params[{idx}] type '{param_type}' is not allowed.",
            )
        elif param_type == "enum" and "enum" not in param:
            _add_issue(
                issues,
                f"SCHEMA_MISSING_FIELD:{path}.enum",
                f"params[{idx}] enum is required for type 'enum'.",
            )

        if "default" not in param:
            _add_issue(
                issues,
                f"SCHEMA_MISSING_FIELD:{path}.default",
                f"params[{idx}] missing default.",
            )
        else:
            default = param.get("default")
            if _is_callable_value(default):
                _add_issue(
                    issues,
                    f"INVALID_TYPE:{path}.default",
                    f"params[{idx}] default must not be callable.",
                )
            if isinstance(param_type, str) and param_type:
                _validate_param_default_type(default, param_type, path, issues)

        if "description" in param and not isinstance(param["description"], str):
            _add_issue(
                issues,
                f"INVALID_TYPE:{path}.description",
                f"params[{idx}] description must be a string.",
            )

        for bound_key in ("min", "max", "step"):
            if bound_key in param and not isinstance(param[bound_key], (int, float)):
                _add_issue(
                    issues,
                    f"INVALID_TYPE:{path}.{bound_key}",
                    f"params[{idx}] {bound_key} must be a number.",
                )

        if "min" in param and "max" in param:
            min_val = param.get("min")
            max_val = param.get("max")
            if isinstance(min_val, (int, float)) and isinstance(max_val, (int, float)):
                if min_val > max_val:
                    _add_issue(
                        issues,
                        f"INVALID_ENUM:{path}.min",
                        f"params[{idx}] min must be <= max.",
                    )

        if "enum" in param:
            enum = param["enum"]
            if not isinstance(enum, list) or not enum:
                _add_issue(
                    issues,
                    f"INVALID_TYPE:{path}.enum",
                    f"params[{idx}] enum must be a non-empty list.",
                )
            else:
                for item in enum:
                    if _is_callable_value(item) or isinstance(item, (dict, list, set, tuple)):
                        _add_issue(
                            issues,
                            f"INVALID_TYPE:{path}.enum",
                            f"params[{idx}] enum values must be scalar.",
                        )
                        break
                default = param.get("default")
                if default not in enum:
                    _add_issue(
                        issues,
                        f"INVALID_ENUM:{path}.default",
                        f"params[{idx}] default must be in enum.",
                    )


def _validate_param_default_type(
    default: Any,
    param_type: str,
    path: str,
    issues: list[ValidationIssue],
) -> None:
    if param_type in {"string", "str"}:
        if not isinstance(default, str):
            _add_issue(
                issues,
                f"INVALID_TYPE:{path}.default",
                "default must be a string.",
            )
    elif param_type == "int":
        if not isinstance(default, int) or isinstance(default, bool):
            _add_issue(
                issues,
                f"INVALID_TYPE:{path}.default",
                "default must be an integer.",
            )
    elif param_type == "float":
        if not isinstance(default, (int, float)) or isinstance(default, bool):
            _add_issue(
                issues,
                f"INVALID_TYPE:{path}.default",
                "default must be a float.",
            )
    elif param_type == "bool":
        if not isinstance(default, bool):
            _add_issue(
                issues,
                f"INVALID_TYPE:{path}.default",
                "default must be a boolean.",
            )


def _validate_interface(
    candidate: PluginCandidate,
    tree: ast.AST,
    issues: list[ValidationIssue],
) -> None:
    defs = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    if "get_schema" not in defs:
        _add_issue(
            issues,
            "INTERFACE_MISSING:get_schema",
            f"{candidate.py_path.name} must define get_schema().",
        )
    if candidate.plugin_type == "indicator":
        if "compute" not in defs:
            _add_issue(
                issues,
                "INTERFACE_MISSING:compute",
                f"{candidate.py_path.name} must define compute(ctx).",
            )
    else:
        if "on_bar" not in defs:
            _add_issue(
                issues,
                "INTERFACE_MISSING:on_bar",
                f"{candidate.py_path.name} must define on_bar(ctx).",
            )


def _validate_global_state(tree: ast.AST, issues: list[ValidationIssue]) -> None:
    scanner = _GlobalStateScanner()
    scanner.visit(tree)
    for issue in scanner.issues:
        _add_issue(issues, issue.code, issue.message)


class _GlobalStateScanner(ast.NodeVisitor):
    _MUTATING_METHODS = {
        "append",
        "extend",
        "insert",
        "remove",
        "discard",
        "pop",
        "clear",
        "update",
        "setdefault",
        "add",
        "sort",
        "reverse",
    }

    def __init__(self) -> None:
        self.issues: list[ValidationIssue] = []
        self._function_depth = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_defaults(node)
        self._check_decorators(node.decorator_list)
        self._function_depth += 1
        self.generic_visit(node)
        self._function_depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_defaults(node)
        self._check_decorators(node.decorator_list)
        self._function_depth += 1
        self.generic_visit(node)
        self._function_depth -= 1

    def visit_Global(self, node: ast.Global) -> None:
        self._add_risk("Global statements are not allowed.")
        self.generic_visit(node)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self._add_risk("Nonlocal statements are not allowed.")
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._function_depth == 0 and not self._is_immutable_assignment(node):
            self._add_risk("Global mutable state is not allowed.")
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if self._function_depth == 0 and not self._is_immutable_assignment(node):
            self._add_risk("Global mutable state is not allowed.")
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if self._function_depth == 0:
            self._add_risk("Global mutable state is not allowed.")
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> None:
        if self._function_depth == 0:
            call = node.value
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute):
                if call.func.attr in self._MUTATING_METHODS:
                    self._add_risk("Global mutable state is not allowed.")
        self.generic_visit(node)

    def _add_risk(self, message: str) -> None:
        key = ("GLOBAL_STATE_RISK", message)
        if any((issue.code, issue.message) == key for issue in self.issues):
            return
        self.issues.append(ValidationIssue(code="GLOBAL_STATE_RISK", message=message))

    def _check_defaults(self, node: ast.AST) -> None:
        defaults: list[ast.AST] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defaults = list(node.args.defaults) + [
                default for default in node.args.kw_defaults if default is not None
            ]
        for default in defaults:
            if self._is_mutable_default(default):
                self._add_risk("Mutable default arguments are not allowed.")

    def _check_decorators(self, decorators: list[ast.AST]) -> None:
        for decorator in decorators:
            name = self._decorator_name(decorator)
            if not name:
                continue
            lowered = name.lower()
            if "cache" in lowered or "memo" in lowered:
                self._add_risk("Caching decorators are not allowed.")

    def _is_mutable_default(self, node: ast.AST) -> bool:
        if isinstance(node, (ast.List, ast.Dict, ast.Set)):
            return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return node.func.id in {"list", "dict", "set"}
        return False

    def _is_immutable_assignment(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Assign):
            value = node.value
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            value = node.value
            targets = [node.target]
        else:
            return False
        if value is None:
            return False
        if not self._is_immutable_expr(value):
            return False
        for target in targets:
            if not isinstance(target, ast.Name):
                return False
            if not target.id.isupper():
                return False
        return True

    def _is_immutable_expr(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Constant):
            return True
        if isinstance(node, ast.Tuple):
            return all(self._is_immutable_expr(elt) for elt in node.elts)
        return False

    def _decorator_name(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Call):
            return self._decorator_name(node.func)
        return None


def _validate_static_safety(tree: ast.AST, issues: list[ValidationIssue]) -> None:
    scanner = _SafetyScanner()
    scanner.collect_bindings(tree)
    scanner.visit(tree)
    for issue in scanner.issues:
        _add_issue(issues, issue.code, issue.message)


def _require_fields(
    payload: dict[str, Any],
    required: list[str],
    issues: list[ValidationIssue],
) -> None:
    for key in required:
        if key not in payload:
            _add_issue(issues, f"SCHEMA_MISSING_FIELD:{key}", f"Missing required field '{key}'.")


def _reject_unknown_fields(
    payload: dict[str, Any],
    allowed: set[str],
    issues: list[ValidationIssue],
) -> None:
    for key in sorted(payload.keys()):
        if key not in allowed:
            _add_issue(issues, f"SCHEMA_UNKNOWN_FIELD:{key}", f"Unknown field '{key}'.")


def _validate_string_list(value: Any, field: str, issues: list[ValidationIssue]) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        _add_issue(issues, f"INVALID_TYPE:{field}", f"{field} must be a list of strings.")


def _ensure_no_callables(value: Any, path: str, issues: list[ValidationIssue]) -> None:
    if _is_callable_value(value):
        _add_issue(issues, f"INVALID_TYPE:{path}", f"{path} must not be callable.")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _ensure_no_callables(item, f"{path}.{key}", issues)
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            _ensure_no_callables(item, f"{path}[{idx}]", issues)


def _is_callable_value(value: Any) -> bool:
    return callable(value)


def _add_issue(issues: list[ValidationIssue], code: str, message: str) -> None:
    key = (code, message)
    if any((issue.code, issue.message) == key for issue in issues):
        return
    issues.append(ValidationIssue(code=code, message=message))


def _extract_meta(payload: dict[str, Any]) -> dict[str, str | None]:
    return {
        "name": _normalize_meta_value(payload.get("name")),
        "version": _normalize_meta_value(payload.get("version")),
        "category": _normalize_meta_value(payload.get("category")),
    }


def _normalize_meta_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _empty_meta() -> dict[str, str | None]:
    return {"name": None, "version": None, "category": None}


def _hash_plugin_dir(plugin_dir: Path, issues: list[ValidationIssue]) -> str:
    hasher = sha256()
    if not plugin_dir.exists():
        _add_issue(issues, "SOURCE_HASH_ERROR", "Plugin directory missing.")
        return ""
    for path in sorted(plugin_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(plugin_dir).as_posix()
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\0")
        try:
            data = path.read_bytes()
        except OSError as exc:
            _add_issue(
                issues,
                "SOURCE_HASH_ERROR",
                f"Failed to read {rel} for hashing: {exc}",
            )
            return ""
        hasher.update(data)
    return hasher.hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

class _SafetyScanner(ast.NodeVisitor):
    _FORBIDDEN_IMPORT_ROOTS = {
        "aiohttp",
        "ctypes",
        "datetime",
        "io",
        "ftplib",
        "http",
        "httpx",
        "importlib",
        "multiprocessing",
        "os",
        "pathlib",
        "random",
        "requests",
        "secrets",
        "shutil",
        "smtplib",
        "socket",
        "subprocess",
        "sys",
        "threading",
        "time",
        "urllib",
        "uuid",
        "websocket",
        "websockets",
    }

    _FORBIDDEN_CALLS = {
        "eval",
        "exec",
        "compile",
        "open",
        "__import__",
        "globals",
        "locals",
    }

    _FORBIDDEN_BUILTIN_ATTRS = {"__dict__", "__class__", "__file__", "__mro__"}

    _NON_DETERMINISTIC_PREFIXES = {
        "random",
        "secrets",
        "uuid",
        "time",
        "datetime",
    }

    _NON_DETERMINISTIC_CALLS = {
        "time.time",
        "time.perf_counter",
        "time.monotonic",
        "time.process_time",
        "datetime.now",
        "datetime.utcnow",
        "uuid.uuid4",
    }

    def __init__(self) -> None:
        self.issues: list[ValidationIssue] = []
        self.aliases: dict[str, str] = {}
        self.bindings: dict[str, str] = {}

    def collect_bindings(self, tree: ast.AST) -> None:
        self._collect_import_aliases(tree)
        _BindingCollector(self).visit(tree)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            module = alias.name
            asname = alias.asname or module.split(".")[0]
            self.aliases[asname] = module
            if self._is_forbidden_import(module):
                self._add_issue(
                    f"FORBIDDEN_IMPORT:{module}",
                    f"Import '{module}' is not allowed.",
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            name = alias.name
            asname = alias.asname or name
            full = f"{module}.{name}" if module else name
            self.aliases[asname] = full
            if self._is_forbidden_import(module or name):
                self._add_issue(
                    f"FORBIDDEN_IMPORT:{full}",
                    f"Import '{full}' is not allowed.",
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            name = node.func.id
            if self._is_forbidden_call_name(name):
                self._add_issue(
                    f"FORBIDDEN_CALL:{name}",
                    f"Call to '{name}' is not allowed.",
                )
            alias_target = self.aliases.get(name)
            if alias_target is None:
                alias_target = self.bindings.get(name)
            if alias_target is not None:
                if self._is_non_deterministic_call(alias_target):
                    self._add_issue(
                        f"NON_DETERMINISTIC_API:{alias_target}",
                        f"Non-deterministic API '{alias_target}' is not allowed.",
                    )
                elif self._is_forbidden_call_target(alias_target):
                    self._add_issue(
                        f"FORBIDDEN_CALL:{alias_target}",
                        f"Call to '{alias_target}' is not allowed.",
                    )
            for forbidden in self._FORBIDDEN_CALLS:
                if self._alias_matches(name, f"builtins.{forbidden}"):
                    self._add_issue(
                        f"FORBIDDEN_CALL:{forbidden}",
                        f"Call to builtins.{forbidden} is not allowed.",
                    )
            if name == "getattr" and self._is_builtins_target(node.args[:1]):
                self._add_issue(
                    "FORBIDDEN_CALL:getattr(__builtins__)",
                    "getattr on __builtins__ is not allowed.",
                )
            if name == "setattr" and self._is_builtins_target(node.args[:1]):
                self._add_issue(
                    "FORBIDDEN_CALL:setattr(__builtins__)",
                    "setattr on __builtins__ is not allowed.",
                )
            if name == "__import__" and self._alias_matches(name, "builtins.__import__"):
                self._add_issue(
                    "FORBIDDEN_CALL:__import__",
                    "Dynamic import via __import__ is not allowed.",
                )

        if isinstance(node.func, ast.Attribute):
            resolved = self._resolve_attribute(node.func)
            if resolved is not None:
                if self._is_forbidden_attribute(resolved):
                    self._add_issue(
                        f"FORBIDDEN_ATTRIBUTE:{resolved}",
                        f"Attribute access '{resolved}' is not allowed.",
                    )
                if self._is_non_deterministic_call(resolved):
                    self._add_issue(
                        f"NON_DETERMINISTIC_API:{resolved}",
                        f"Non-deterministic API '{resolved}' is not allowed.",
                    )
                if resolved.endswith(".getattr") and self._is_builtins_target(node.args[:1]):
                    self._add_issue(
                        "FORBIDDEN_CALL:getattr(__builtins__)",
                        "getattr on __builtins__ is not allowed.",
                    )
                if resolved.endswith(".setattr") and self._is_builtins_target(node.args[:1]):
                    self._add_issue(
                        "FORBIDDEN_CALL:setattr(__builtins__)",
                        "setattr on __builtins__ is not allowed.",
                    )
            else:
                self._add_issue(
                    "AST_UNCERTAIN",
                    "Unable to resolve attribute call safely.",
                )
            if self._is_path_io_call(node.func):
                self._add_issue(
                    "FORBIDDEN_CALL:Path.open",
                    "Path read/write operations are not allowed.",
                )
            if self._is_subprocess_call(node.func):
                self._add_issue(
                    "FORBIDDEN_CALL:subprocess",
                    "subprocess usage is not allowed.",
                )
            if self._is_os_call(node.func):
                self._add_issue(
                    "FORBIDDEN_CALL:os",
                    "os.system/os.popen are not allowed.",
                )
        if not isinstance(node.func, (ast.Name, ast.Attribute)):
            self._add_issue(
                "AST_UNCERTAIN",
                "Unable to resolve call target safely.",
            )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in self._FORBIDDEN_BUILTIN_ATTRS:
            self._add_issue(
                f"FORBIDDEN_ATTRIBUTE:{node.attr}",
                f"Access to {node.attr} is not allowed.",
            )
        resolved = self._resolve_attribute(node)
        if resolved is not None:
            if self._is_forbidden_attribute(resolved):
                self._add_issue(
                    f"FORBIDDEN_ATTRIBUTE:{resolved}",
                    f"Attribute access '{resolved}' is not allowed.",
                )
        else:
            self._add_issue(
                "AST_UNCERTAIN",
                "Unable to resolve attribute access safely.",
            )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        self._record_bindings(node.targets, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        targets = [node.target]
        self._record_bindings(targets, node.value)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in {"__file__", "__dict__", "__class__", "__builtins__"}:
            self._add_issue(
                f"FORBIDDEN_ATTRIBUTE:{node.id}",
                f"Access to {node.id} is not allowed.",
            )
        self.generic_visit(node)

    def _add_issue(self, code: str, message: str) -> None:
        key = (code, message)
        if any((issue.code, issue.message) == key for issue in self.issues):
            return
        self.issues.append(ValidationIssue(code=code, message=message))

    def _collect_import_aliases(self, tree: ast.AST) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name
                    asname = alias.asname or module.split(".")[0]
                    self.aliases[asname] = module
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    name = alias.name
                    asname = alias.asname or name
                    full = f"{module}.{name}" if module else name
                    self.aliases[asname] = full

    def _record_bindings(self, targets: list[ast.expr], value: ast.AST | None) -> None:
        if value is None:
            return
        resolved = self._resolve_binding_value(value)
        if resolved is None:
            return
        for target in targets:
            if isinstance(target, ast.Name):
                self.bindings[target.id] = resolved

    def _resolve_binding_value(self, value: ast.AST) -> str | None:
        if isinstance(value, ast.Name):
            return self._resolve_name(value.id)
        if isinstance(value, ast.Attribute):
            return self._resolve_attribute(value)
        if isinstance(value, ast.Call) and self._is_path_constructor(value.func):
            return "pathlib.Path"
        return None

    def _resolve_name(self, name: str) -> str:
        if name in self.bindings:
            return self.bindings[name]
        if name in self.aliases:
            return self.aliases[name]
        return name

    def _is_forbidden_import(self, module: str) -> bool:
        root = module.split(".")[0]
        return root in self._FORBIDDEN_IMPORT_ROOTS

    def _is_forbidden_call_name(self, name: str) -> bool:
        return name in self._FORBIDDEN_CALLS

    def _alias_matches(self, name: str, module_prefix: str) -> bool:
        module = self.aliases.get(name) or self.bindings.get(name)
        if module is None:
            return False
        return module == module_prefix or module.startswith(f"{module_prefix}.")

    def _resolve_attribute(self, node: ast.Attribute) -> str | None:
        parts: list[str] = []
        current: ast.AST = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            root = current.id
            resolved_root = self.bindings.get(root) or self.aliases.get(root, root)
            resolved_parts = [resolved_root] + list(reversed(parts))
            return ".".join(resolved_parts)
        return None

    def _is_forbidden_attribute(self, resolved: str) -> bool:
        root = resolved.split(".")[0]
        if root in self._FORBIDDEN_IMPORT_ROOTS:
            return True
        if resolved.startswith("builtins."):
            attr = resolved.split(".", 1)[1]
            if attr in self._FORBIDDEN_CALLS:
                return True
        return False

    def _is_forbidden_call_target(self, resolved: str) -> bool:
        if resolved in self._FORBIDDEN_CALLS:
            return True
        root = resolved.split(".")[0]
        if root in self._FORBIDDEN_IMPORT_ROOTS:
            return True
        if resolved.startswith("builtins."):
            attr = resolved.split(".", 1)[1]
            if attr in self._FORBIDDEN_CALLS:
                return True
        return False

    def _is_non_deterministic_call(self, resolved: str) -> bool:
        if resolved in self._NON_DETERMINISTIC_CALLS:
            return True
        root = resolved.split(".")[0]
        if root in self._NON_DETERMINISTIC_PREFIXES:
            return True
        return False

    def _is_builtins_target(self, args: list[ast.AST]) -> bool:
        if not args:
            return False
        target = args[0]
        if isinstance(target, ast.Name) and target.id == "__builtins__":
            return True
        if isinstance(target, ast.Name) and target.id == "builtins":
            return True
        if isinstance(target, ast.Name) and self._alias_matches(target.id, "builtins"):
            return True
        return False

    def _is_path_io_call(self, node: ast.Attribute) -> bool:
        if node.attr not in {"open", "read_text", "read_bytes", "write_text", "write_bytes"}:
            return False
        return isinstance(node.value, ast.Call) and self._is_path_constructor(node.value.func)

    def _is_path_constructor(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            return node.id == "Path" or self._alias_matches(node.id, "pathlib.Path")
        if isinstance(node, ast.Attribute):
            return node.attr == "Path"
        return False

    def _is_subprocess_call(self, node: ast.Attribute) -> bool:
        return (
            isinstance(node.value, ast.Name)
            and self._alias_matches(node.value.id, "subprocess")
        )

    def _is_os_call(self, node: ast.Attribute) -> bool:
        if node.attr not in {"system", "popen"}:
            return False
        return isinstance(node.value, ast.Name) and self._alias_matches(node.value.id, "os")


class _BindingCollector(ast.NodeVisitor):
    def __init__(self, scanner: _SafetyScanner) -> None:
        self._scanner = scanner

    def visit_Assign(self, node: ast.Assign) -> None:
        self._scanner._record_bindings(node.targets, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._scanner._record_bindings([node.target], node.value)
        self.generic_visit(node)
