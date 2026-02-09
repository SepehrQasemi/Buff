from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

try:
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - PyYAML is a dependency, but keep fallback.
    yaml = None

from .discovery import PluginCandidate, PluginType

ValidationStatus = Literal["PASS", "FAIL"]

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
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class ValidationError:
    rule_id: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    plugin_id: str
    plugin_type: PluginType
    fingerprint: str
    status: ValidationStatus
    errors: list[ValidationError]
    validated_at_utc: str
    meta: dict[str, str | None]


def validate_all(candidates: Iterable[PluginCandidate], out_dir: Path) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    for candidate in candidates:
        result = validate_candidate(candidate)
        write_validation_artifact(result, out_dir)
        results.append(result)
    return results


def validate_candidate(candidate: PluginCandidate) -> ValidationResult:
    try:
        return _validate_candidate(candidate)
    except Exception as exc:  # pragma: no cover - hard fail-closed guard.
        errors = [
            ValidationError(
                rule_id="VALIDATOR_CRASH",
                message=f"Validator crashed: {exc}",
            )
        ]
        return _result(candidate, errors, _empty_meta())


def write_validation_artifact(result: ValidationResult, out_dir: Path) -> None:
    out_root = Path(out_dir)
    dest = out_root / result.plugin_type / result.plugin_id / "validation.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "plugin_id": result.plugin_id,
        "plugin_type": result.plugin_type,
        "fingerprint": result.fingerprint,
        "status": result.status,
        "errors": [error.__dict__ for error in result.errors],
        "validated_at_utc": result.validated_at_utc,
        "meta": result.meta,
    }
    dest.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _validate_candidate(candidate: PluginCandidate) -> ValidationResult:
    errors: list[ValidationError] = []
    meta = _empty_meta()
    yaml_payload = _load_yaml(candidate.yaml_path, errors)
    if yaml_payload is not None:
        meta = _extract_meta(yaml_payload)
        if candidate.plugin_type == "indicator":
            _validate_indicator_schema(candidate, yaml_payload, errors)
        else:
            _validate_strategy_schema(candidate, yaml_payload, errors)

    py_source, py_tree = _load_python(candidate.py_path, errors)
    if py_tree is not None:
        _validate_interface(candidate, py_tree, errors)
        _validate_static_safety(py_tree, errors)

    return _result(candidate, errors, meta)


def _result(
    candidate: PluginCandidate, errors: list[ValidationError], meta: dict[str, str | None]
) -> ValidationResult:
    status: ValidationStatus = "PASS" if not errors else "FAIL"
    return ValidationResult(
        plugin_id=candidate.plugin_id,
        plugin_type=candidate.plugin_type,
        fingerprint=candidate.fingerprint,
        status=status,
        errors=errors,
        validated_at_utc=datetime.now(timezone.utc).isoformat(),
        meta=meta,
    )


def _load_yaml(path: Path, errors: list[ValidationError]) -> dict[str, Any] | None:
    if not path.exists():
        _add_error(errors, "MISSING_FILE", f"{path.name} is missing.")
        return None
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        _add_error(errors, "YAML_READ_ERROR", f"Failed to read {path.name}: {exc}")
        return None
    try:
        if yaml is None:
            payload = json.loads(raw)
        else:
            payload = yaml.safe_load(raw)
    except Exception as exc:
        _add_error(errors, "YAML_PARSE_ERROR", f"Failed to parse {path.name}: {exc}")
        return None
    if not isinstance(payload, dict):
        _add_error(errors, "YAML_INVALID", f"{path.name} must be a mapping.")
        return None
    return payload


def _load_python(path: Path, errors: list[ValidationError]) -> tuple[str | None, ast.AST | None]:
    if not path.exists():
        _add_error(errors, "MISSING_FILE", f"{path.name} is missing.")
        return None, None
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        _add_error(errors, "PYTHON_READ_ERROR", f"Failed to read {path.name}: {exc}")
        return None, None
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        _add_error(errors, "PYTHON_PARSE_ERROR", f"{path.name} syntax error: {exc.msg}")
        return source, None
    return source, tree


def _validate_indicator_schema(
    candidate: PluginCandidate,
    payload: dict[str, Any],
    errors: list[ValidationError],
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
    _require_fields(payload, required, "indicator.yaml", errors)
    _validate_common_schema(candidate, payload, errors, ALLOWED_INDICATOR_CATEGORIES)

    inputs = payload.get("inputs")
    if inputs is not None:
        _validate_string_list(inputs, "inputs", "indicator.yaml", errors)
    outputs = payload.get("outputs")
    if outputs is not None:
        _validate_string_list(outputs, "outputs", "indicator.yaml", errors)

    params = payload.get("params")
    if params is not None:
        _validate_params(params, "indicator.yaml", errors)

    nan_policy = payload.get("nan_policy")
    if nan_policy is not None and nan_policy not in ALLOWED_NAN_POLICIES:
        _add_error(
            errors,
            "SCHEMA_VALUE_INVALID",
            "indicator.yaml nan_policy must be one of propagate, fill, error.",
        )


def _validate_strategy_schema(
    candidate: PluginCandidate,
    payload: dict[str, Any],
    errors: list[ValidationError],
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
    _require_fields(payload, required, "strategy.yaml", errors)
    _validate_common_schema(candidate, payload, errors, ALLOWED_STRATEGY_CATEGORIES)

    inputs = payload.get("inputs")
    if inputs is not None:
        if not isinstance(inputs, dict):
            _add_error(errors, "SCHEMA_TYPE_INVALID", "strategy.yaml inputs must be a mapping.")
        else:
            if "series" not in inputs:
                _add_error(
                    errors,
                    "SCHEMA_MISSING_FIELD",
                    "strategy.yaml inputs.series is required.",
                )
            else:
                _validate_string_list(
                    inputs.get("series"), "inputs.series", "strategy.yaml", errors
                )
            if "indicators" not in inputs:
                _add_error(
                    errors,
                    "SCHEMA_MISSING_FIELD",
                    "strategy.yaml inputs.indicators is required.",
                )
            else:
                _validate_string_list(
                    inputs.get("indicators"), "inputs.indicators", "strategy.yaml", errors
                )

    outputs = payload.get("outputs")
    if outputs is not None:
        if not isinstance(outputs, dict):
            _add_error(errors, "SCHEMA_TYPE_INVALID", "strategy.yaml outputs must be a mapping.")
        else:
            if "intents" not in outputs:
                _add_error(
                    errors,
                    "SCHEMA_MISSING_FIELD",
                    "strategy.yaml outputs.intents is required.",
                )
            else:
                intents = outputs.get("intents")
                _validate_string_list(intents, "outputs.intents", "strategy.yaml", errors)
                if isinstance(intents, list):
                    invalid = [intent for intent in intents if intent not in ALLOWED_INTENTS]
                    if invalid:
                        _add_error(
                            errors,
                            "SCHEMA_VALUE_INVALID",
                            f"strategy.yaml intents contain invalid values: {sorted(invalid)}.",
                        )
            if "provides_confidence" not in outputs:
                _add_error(
                    errors,
                    "SCHEMA_MISSING_FIELD",
                    "strategy.yaml outputs.provides_confidence is required.",
                )
            else:
                provides_confidence = outputs.get("provides_confidence")
                if provides_confidence is not None and not isinstance(provides_confidence, bool):
                    _add_error(
                        errors,
                        "SCHEMA_TYPE_INVALID",
                        "strategy.yaml outputs.provides_confidence must be a boolean.",
                    )

    params = payload.get("params")
    if params is not None:
        _validate_params(params, "strategy.yaml", errors)


def _validate_common_schema(
    candidate: PluginCandidate,
    payload: dict[str, Any],
    errors: list[ValidationError],
    allowed_categories: set[str],
) -> None:
    plugin_id = payload.get("id")
    if isinstance(plugin_id, str):
        if not plugin_id:
            _add_error(errors, "SCHEMA_VALUE_INVALID", "Schema id must be non-empty.")
        elif not ID_RE.match(plugin_id):
            _add_error(
                errors,
                "SCHEMA_VALUE_INVALID",
                "Schema id must be snake_case (lowercase letters, numbers, underscores).",
            )
        if plugin_id != candidate.plugin_id:
            _add_error(
                errors,
                "SCHEMA_ID_MISMATCH",
                f"Schema id '{plugin_id}' does not match directory '{candidate.plugin_id}'.",
            )
    elif plugin_id is not None:
        _add_error(errors, "SCHEMA_TYPE_INVALID", "Schema id must be a string.")

    name = payload.get("name")
    if name is not None and not isinstance(name, str):
        _add_error(errors, "SCHEMA_TYPE_INVALID", "Schema name must be a string.")

    version = payload.get("version")
    if isinstance(version, str):
        if not SEMVER_RE.match(version):
            _add_error(errors, "SCHEMA_VALUE_INVALID", "Schema version must be semver (x.y.z).")
    elif version is not None:
        _add_error(errors, "SCHEMA_TYPE_INVALID", "Schema version must be a string.")

    category = payload.get("category")
    if isinstance(category, str):
        if category not in allowed_categories:
            _add_error(
                errors,
                "SCHEMA_VALUE_INVALID",
                f"Schema category '{category}' is not allowed.",
            )
    elif category is not None:
        _add_error(errors, "SCHEMA_TYPE_INVALID", "Schema category must be a string.")

    warmup_bars = payload.get("warmup_bars")
    if warmup_bars is not None:
        if not isinstance(warmup_bars, int):
            _add_error(errors, "SCHEMA_TYPE_INVALID", "warmup_bars must be an integer.")
        elif warmup_bars < 0:
            _add_error(errors, "SCHEMA_VALUE_INVALID", "warmup_bars must be >= 0.")


def _validate_params(params: Any, source: str, errors: list[ValidationError]) -> None:
    if not isinstance(params, list):
        _add_error(errors, "SCHEMA_TYPE_INVALID", f"{source} params must be a list.")
        return
    for idx, param in enumerate(params):
        if not isinstance(param, dict):
            _add_error(
                errors,
                "SCHEMA_TYPE_INVALID",
                f"{source} params[{idx}] must be a mapping.",
            )
            continue
        name = param.get("name")
        if not isinstance(name, str) or not name:
            _add_error(
                errors,
                "SCHEMA_VALUE_INVALID",
                f"{source} params[{idx}] missing name.",
            )
        param_type = param.get("type")
        if not isinstance(param_type, str) or not param_type:
            _add_error(
                errors,
                "SCHEMA_VALUE_INVALID",
                f"{source} params[{idx}] missing type.",
            )
        if "default" not in param:
            _add_error(
                errors,
                "SCHEMA_VALUE_INVALID",
                f"{source} params[{idx}] missing default.",
            )
        if "description" in param and not isinstance(param["description"], str):
            _add_error(
                errors,
                "SCHEMA_TYPE_INVALID",
                f"{source} params[{idx}] description must be a string.",
            )
        for bound_key in ("min", "max", "step"):
            if bound_key in param and not isinstance(param[bound_key], (int, float)):
                _add_error(
                    errors,
                    "SCHEMA_TYPE_INVALID",
                    f"{source} params[{idx}] {bound_key} must be a number.",
                )
        if "min" in param and "max" in param:
            min_val = param.get("min")
            max_val = param.get("max")
            if isinstance(min_val, (int, float)) and isinstance(max_val, (int, float)):
                if min_val > max_val:
                    _add_error(
                        errors,
                        "SCHEMA_VALUE_INVALID",
                        f"{source} params[{idx}] min must be <= max.",
                    )
        if "enum" in param:
            enum = param["enum"]
            if not isinstance(enum, list) or not enum:
                _add_error(
                    errors,
                    "SCHEMA_TYPE_INVALID",
                    f"{source} params[{idx}] enum must be a non-empty list.",
                )
            else:
                default = param.get("default")
                if default not in enum:
                    _add_error(
                        errors,
                        "SCHEMA_VALUE_INVALID",
                        f"{source} params[{idx}] default must be in enum.",
                    )


def _validate_interface(
    candidate: PluginCandidate,
    tree: ast.AST,
    errors: list[ValidationError],
) -> None:
    defs = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    if "get_schema" not in defs:
        _add_error(
            errors,
            "INTERFACE_MISSING",
            f"{candidate.py_path.name} must define get_schema().",
        )
    if candidate.plugin_type == "indicator":
        if "compute" not in defs:
            _add_error(
                errors,
                "INTERFACE_MISSING",
                f"{candidate.py_path.name} must define compute(ctx).",
            )
    else:
        if "on_bar" not in defs:
            _add_error(
                errors,
                "INTERFACE_MISSING",
                f"{candidate.py_path.name} must define on_bar(ctx).",
            )


def _validate_static_safety(tree: ast.AST, errors: list[ValidationError]) -> None:
    scanner = _SafetyScanner()
    scanner.visit(tree)
    for rule_id, message in scanner.errors:
        _add_error(errors, rule_id, message)


def _require_fields(
    payload: dict[str, Any],
    required: list[str],
    source: str,
    errors: list[ValidationError],
) -> None:
    for key in required:
        if key not in payload:
            _add_error(errors, "SCHEMA_MISSING_FIELD", f"{source} missing required field '{key}'.")


def _validate_string_list(
    value: Any,
    field: str,
    source: str,
    errors: list[ValidationError],
) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        _add_error(errors, "SCHEMA_TYPE_INVALID", f"{source} {field} must be a list of strings.")


def _add_error(errors: list[ValidationError], rule_id: str, message: str) -> None:
    key = (rule_id, message)
    if any((err.rule_id, err.message) == key for err in errors):
        return
    errors.append(ValidationError(rule_id=rule_id, message=message))


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


class _SafetyScanner(ast.NodeVisitor):
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

    def __init__(self) -> None:
        self.errors: list[tuple[str, str]] = []
        self.aliases: dict[str, str] = {}

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            module = alias.name
            asname = alias.asname or module.split(".")[0]
            self.aliases[asname] = module
            if self._is_forbidden_import(module):
                self._add("FORBIDDEN_IMPORT", f"Import '{module}' is not allowed.")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            name = alias.name
            asname = alias.asname or name
            full = f"{module}.{name}" if module else name
            self.aliases[asname] = full
            if self._is_forbidden_import_from(module, name):
                self._add("FORBIDDEN_IMPORT", f"Import '{full}' is not allowed.")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id == "open":
            self._add("FORBIDDEN_OPERATION", "builtins.open() is not allowed.")
        if isinstance(node.func, ast.Attribute):
            if self._is_builtin_open(node.func):
                self._add("FORBIDDEN_OPERATION", "builtins.open() is not allowed.")
            if self._is_path_write_call(node.func):
                self._add(
                    "FORBIDDEN_OPERATION",
                    "Path(...).write* operations are not allowed.",
                )
            if self._is_time_call(node.func):
                self._add("FORBIDDEN_OPERATION", "time.time() is not allowed.")
            if self._is_datetime_now(node.func):
                self._add(
                    "FORBIDDEN_OPERATION",
                    "datetime.now()/utcnow()/today() is not allowed.",
                )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if self._is_numpy_random(node):
            self._add("FORBIDDEN_OPERATION", "numpy.random usage is not allowed.")
        if self._is_pandas_io(node):
            self._add("FORBIDDEN_OPERATION", "pandas read_/to_ operations are not allowed.")
        self.generic_visit(node)

    def _add(self, rule_id: str, message: str) -> None:
        key = (rule_id, message)
        if key not in self.errors:
            self.errors.append(key)

    def _is_forbidden_import(self, module: str) -> bool:
        if module.startswith("numpy.random"):
            return True
        root = module.split(".")[0]
        return root in self._FORBIDDEN_IMPORT_ROOTS

    def _is_forbidden_import_from(self, module: str, name: str) -> bool:
        root = module.split(".")[0] if module else name.split(".")[0]
        if root in self._FORBIDDEN_IMPORT_ROOTS:
            return True
        if module.startswith("numpy.random"):
            return True
        if module == "numpy" and name == "random":
            return True
        if module == "pandas" and (name.startswith("read_") or name.startswith("to_")):
            return True
        if module == "builtins" and name == "open":
            return True
        return False

    def _alias_matches(self, name: str, module_prefix: str) -> bool:
        module = self.aliases.get(name)
        if module is None:
            return False
        return module == module_prefix or module.startswith(f"{module_prefix}.")

    def _is_builtin_open(self, node: ast.Attribute) -> bool:
        return (
            isinstance(node.value, ast.Name)
            and node.attr == "open"
            and (node.value.id == "builtins" or self._alias_matches(node.value.id, "builtins"))
        )

    def _is_path_write_call(self, node: ast.Attribute) -> bool:
        if node.attr not in {"write", "write_text", "write_bytes", "open"}:
            return False
        return isinstance(node.value, ast.Call) and self._is_path_constructor(node.value.func)

    def _is_path_constructor(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            return node.id == "Path"
        if isinstance(node, ast.Attribute):
            return node.attr == "Path"
        return False

    def _is_time_call(self, node: ast.Attribute) -> bool:
        return (
            node.attr == "time"
            and isinstance(node.value, ast.Name)
            and self._alias_matches(node.value.id, "time")
        )

    def _is_datetime_now(self, node: ast.Attribute) -> bool:
        if node.attr not in {"now", "utcnow", "today"}:
            return False
        if isinstance(node.value, ast.Name) and self._alias_matches(node.value.id, "datetime"):
            return True
        if isinstance(node.value, ast.Attribute) and node.value.attr == "datetime":
            return True
        return False

    def _is_numpy_random(self, node: ast.Attribute) -> bool:
        if isinstance(node.value, ast.Name) and node.attr == "random":
            return self._alias_matches(node.value.id, "numpy")
        if isinstance(node.value, ast.Name):
            return self._alias_matches(node.value.id, "numpy.random")
        return False

    def _is_pandas_io(self, node: ast.Attribute) -> bool:
        if not (node.attr.startswith("read_") or node.attr.startswith("to_")):
            return False
        if isinstance(node.value, ast.Name):
            return self._alias_matches(node.value.id, "pandas")
        return False
