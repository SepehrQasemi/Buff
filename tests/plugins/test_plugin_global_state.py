from __future__ import annotations

from pathlib import Path

from src.plugins.discovery import discover_plugins
from src.plugins.validation import validate_candidate

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


def _validate_indicator(tmp_path: Path, plugin_id: str, py_content: str) -> object:
    yaml_path = tmp_path / f"user_indicators/{plugin_id}/indicator.yaml"
    py_path = tmp_path / f"user_indicators/{plugin_id}/indicator.py"
    _write(yaml_path, BASE_INDICATOR_YAML.replace("demo_indicator", plugin_id))
    _write(py_path, py_content)
    candidate = _candidate(tmp_path, plugin_id)
    return validate_candidate(candidate)


def test_module_level_mutable_assignment_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_global_list",
        "CACHE = []\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert "GLOBAL_STATE_RISK" in result.reason_codes


def test_module_level_mutation_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_global_mutation",
        "CACHE = []\nCACHE.append(1)\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert "GLOBAL_STATE_RISK" in result.reason_codes


def test_global_keyword_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_global_keyword",
        "counter = 0\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    global counter\n    counter += 1\n    return {'value': counter}\n",
    )
    assert result.status == "INVALID"
    assert "GLOBAL_STATE_RISK" in result.reason_codes


def test_default_mutable_args_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_default_arg",
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx, cache=[]):\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert "GLOBAL_STATE_RISK" in result.reason_codes


def test_uppercase_immutable_constants_are_allowed(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "safe_constants",
        "WINDOW = 14\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    return {'value': WINDOW}\n",
    )
    assert result.status == "VALID"
    assert result.reason_codes == []


def test_module_level_attribute_assignment_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_attr_assign",
        "class Box:\n    pass\n\n"
        "box = Box()\n"
        "box.value = 1\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    return {'value': box.value}\n",
    )
    assert result.status == "INVALID"
    assert "GLOBAL_STATE_RISK" in result.reason_codes


def test_caching_decorator_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_cache_decorator",
        "from functools import lru_cache\n\n"
        "@lru_cache()\n"
        "def helper(x):\n    return x\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    return {'value': helper(1)}\n",
    )
    assert result.status == "INVALID"
    assert "GLOBAL_STATE_RISK" in result.reason_codes


def test_pure_functions_are_allowed(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "safe_pure",
        "def helper(x):\n    return x + 1\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    return {'value': helper(1)}\n",
    )
    assert result.status == "VALID"
    assert result.reason_codes == []
