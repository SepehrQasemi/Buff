from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.plugins.discovery import PluginCandidate, discover_plugins
from src.plugins.reason_codes import is_allowed_reason_code
from src.plugins.registry import _load_artifact_details
from src.plugins import validation as plugin_validation
from src.plugins.validation import MAX_PLUGIN_SOURCE_BYTES, validate_all, validate_candidate

BASE_INDICATOR_YAML = """\
id: demo_indicator
name: Demo
version: 1.0.0
category: momentum
inputs: [close]
outputs: [value]
params: []
warmup_bars: 1
nan_policy: propagate
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _candidate(root: Path, plugin_id: str) -> object:
    for candidate in discover_plugins(root):
        if candidate.plugin_type == "indicator" and candidate.plugin_id == plugin_id:
            return candidate
    raise AssertionError("candidate not found")


def _validate_indicator(
    tmp_path: Path, plugin_id: str, py_content: str, yaml_content: str | None = None
):
    yaml_path = tmp_path / f"user_indicators/{plugin_id}/indicator.yaml"
    py_path = tmp_path / f"user_indicators/{plugin_id}/indicator.py"
    _write(yaml_path, yaml_content or BASE_INDICATOR_YAML.replace("demo_indicator", plugin_id))
    _write(py_path, py_content)
    candidate = _candidate(tmp_path, plugin_id)
    return validate_candidate(candidate)


def test_reason_code_allowlist(monkeypatch, tmp_path: Path) -> None:
    codes: set[str] = set()

    result = _validate_indicator(
        tmp_path,
        "bad_yaml",
        "def get_schema():\n    return {}\n\ndef compute(ctx):\n    return {'value': 1}\n",
        "id: bad_yaml\nname: [unterminated\n",
    )
    codes.update(result.reason_codes)

    yaml_only = tmp_path / "user_indicators/missing_py/indicator.yaml"
    _write(yaml_only, BASE_INDICATOR_YAML.replace("demo_indicator", "missing_py"))
    candidate = _candidate(tmp_path, "missing_py")
    codes.update(validate_candidate(candidate).reason_codes)

    py_only = tmp_path / "user_indicators/missing_yaml/indicator.py"
    _write(
        py_only,
        "def get_schema():\n    return {}\n\ndef compute(ctx):\n    return {'value': 1}\n",
    )
    candidate = _candidate(tmp_path, "missing_yaml")
    codes.update(validate_candidate(candidate).reason_codes)

    result = _validate_indicator(
        tmp_path,
        "schema_missing",
        "def get_schema():\n    return {}\n\ndef compute(ctx):\n    return {'value': 1}\n",
        "id: schema_missing\nname: Missing\nversion: 1.0.0\ncategory: momentum\n",
    )
    codes.update(result.reason_codes)

    result = _validate_indicator(
        tmp_path,
        "schema_unknown",
        "def get_schema():\n    return {}\n\ndef compute(ctx):\n    return {'value': 1}\n",
        BASE_INDICATOR_YAML.replace("demo_indicator", "schema_unknown") + "unexpected: 1\n",
    )
    codes.update(result.reason_codes)

    result = _validate_indicator(
        tmp_path,
        "invalid_enum",
        "def get_schema():\n    return {}\n\ndef compute(ctx):\n    return {'value': 1}\n",
        BASE_INDICATOR_YAML.replace("demo_indicator", "invalid_enum").replace(
            "category: momentum", "category: nope"
        ),
    )
    codes.update(result.reason_codes)

    result = _validate_indicator(
        tmp_path,
        "invalid_type",
        "def get_schema():\n    return {}\n\ndef compute(ctx):\n    return {'value': 1}\n",
        BASE_INDICATOR_YAML.replace("demo_indicator", "invalid_type").replace(
            "warmup_bars: 1", "warmup_bars: nope"
        ),
    )
    codes.update(result.reason_codes)

    result = _validate_indicator(
        tmp_path,
        "missing_interface",
        "def get_schema():\n    return {}\n",
    )
    codes.update(result.reason_codes)

    result = _validate_indicator(
        tmp_path,
        "global_state",
        "x = []\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    return {'value': 1}\n",
    )
    codes.update(result.reason_codes)

    result = _validate_indicator(
        tmp_path,
        "forbidden_import",
        "import os\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    return {'value': 1}\n",
    )
    codes.update(result.reason_codes)

    result = _validate_indicator(
        tmp_path,
        "forbidden_call",
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    open('x')\n    return {'value': 1}\n",
    )
    codes.update(result.reason_codes)

    result = _validate_indicator(
        tmp_path,
        "forbidden_attribute",
        "import os\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    os.system('echo hi')\n    return {'value': 1}\n",
    )
    codes.update(result.reason_codes)

    result = _validate_indicator(
        tmp_path,
        "nondeterministic",
        "from datetime import datetime\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    datetime.now()\n    return {'value': 1}\n",
    )
    codes.update(result.reason_codes)

    result = _validate_indicator(
        tmp_path,
        "ast_uncertain",
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    (lambda x: x)(1)\n    return {'value': 1}\n",
    )
    codes.update(result.reason_codes)

    result = _validate_indicator(
        tmp_path,
        "ast_parse_error",
        "def get_schema():\n    return {}\n\ndef compute(ctx):\n    return {\n",
    )
    codes.update(result.reason_codes)

    padding = "x = 1\n"
    repeats = (MAX_PLUGIN_SOURCE_BYTES // len(padding)) + 10
    large_source = (
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    return {'value': 1}\n\n" + padding * repeats
    )
    result = _validate_indicator(
        tmp_path,
        "too_large",
        large_source,
    )
    codes.update(result.reason_codes)

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    candidate = _candidate(tmp_path, "missing_yaml")
    original_load_yaml = plugin_validation._load_yaml
    monkeypatch.setattr("src.plugins.validation._load_yaml", boom)
    codes.update(validate_candidate(candidate).reason_codes)
    monkeypatch.setattr("src.plugins.validation._load_yaml", original_load_yaml)

    missing_dir = tmp_path / "missing_dir"
    missing_candidate = PluginCandidate(
        plugin_id="missing_dir",
        plugin_type="indicator",
        plugin_dir=missing_dir,
        yaml_path=missing_dir / "indicator.yaml",
        py_path=missing_dir / "indicator.py",
        extra_files=[],
    )
    codes.update(validate_candidate(missing_candidate).reason_codes)

    artifacts_root = tmp_path / "artifacts"
    entry = {"plugin_type": "indicator", "id": "missing_artifact"}
    codes.update(_load_artifact_details(artifacts_root, entry).get("reason_codes", []))

    bad_artifact = artifacts_root / "plugin_validation/indicator/bad.json"
    _write(bad_artifact, "{invalid")
    entry = {"plugin_type": "indicator", "id": "bad"}
    codes.update(_load_artifact_details(artifacts_root, entry).get("reason_codes", []))

    def fail_write(*_args, **_kwargs):
        raise OSError("write failed")

    monkeypatch.setattr("src.plugins.validation.write_validation_artifact", fail_write)
    valid_candidate = _candidate(tmp_path, "schema_unknown")
    results = validate_all([valid_candidate], artifacts_root / "plugin_validation")
    for result in results:
        codes.update(result.reason_codes)

    assert codes
    for code in sorted(codes):
        assert is_allowed_reason_code(code), f"unexpected reason code: {code}"


def test_too_large_triggers_invalid(tmp_path: Path) -> None:
    padding = "x = 1\n"
    repeats = (MAX_PLUGIN_SOURCE_BYTES // len(padding)) + 10
    large_source = (
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    return {'value': 1}\n\n" + padding * repeats
    )
    result = _validate_indicator(tmp_path, "too_large_only", large_source)
    assert result.status == "INVALID"
    assert "TOO_LARGE" in result.reason_codes


def test_normal_source_not_too_large(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "normal",
        "def get_schema():\n    return {}\n\ndef compute(ctx):\n    return {'value': 1}\n",
    )
    assert result.status == "VALID"
    assert "TOO_LARGE" not in result.reason_codes


def test_reason_code_allowlist_exhaustive_source_scan() -> None:
    files = [
        Path("src/plugins/validation.py"),
        Path("src/plugins/registry.py"),
    ]
    codes: set[str] = set()
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        codes.update(_extract_reason_codes(tree))

    assert codes
    for code in sorted(codes):
        assert is_allowed_reason_code(code), f"unexpected reason code: {code}"


def _extract_reason_codes(tree: ast.AST) -> set[str]:
    codes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "_add_issue":
                code = _const_str(node.args[1] if len(node.args) > 1 else None)
                if code:
                    codes.add(code)
            elif isinstance(func, ast.Attribute) and func.attr == "_add_issue":
                code = _const_str(node.args[0] if node.args else None)
                if code:
                    codes.add(code)
            elif isinstance(func, ast.Name) and func.id == "ValidationIssue":
                for kw in node.keywords:
                    if kw.arg == "code":
                        code = _const_str(kw.value)
                        if code:
                            codes.add(code)
                if node.args:
                    code = _const_str(node.args[0])
                    if code:
                        codes.add(code)
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "reason_codes":
                    for item in _iter_const_strs(value):
                        codes.add(item)
    return codes


def _const_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _iter_const_strs(node: ast.AST | None) -> list[str]:
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        items: list[str] = []
        for item in node.elts:
            value = _const_str(item)
            if value is not None:
                items.append(value)
        return items
    value = _const_str(node)
    return [value] if value is not None else []
