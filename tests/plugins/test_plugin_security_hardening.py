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


def test_yaml_corruption_is_invalid(tmp_path: Path) -> None:
    yaml_path = tmp_path / "user_indicators/bad/indicator.yaml"
    py_path = tmp_path / "user_indicators/bad/indicator.py"
    _write(yaml_path, "id: bad\nname: [unterminated\n")
    _write(
        py_path, "def get_schema():\n    return {}\n\ndef compute(ctx):\n    return {'value': 0}\n"
    )
    candidate = _candidate(tmp_path, "bad")
    result = validate_candidate(candidate)
    assert result.status == "INVALID"
    assert "YAML_PARSE_ERROR" in result.reason_codes


def test_forbidden_import_os(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_os",
        "import os\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert any(code.startswith("FORBIDDEN_IMPORT:os") for code in result.reason_codes)


def test_forbidden_importlib_usage(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_importlib",
        "import importlib\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    importlib.import_module('os')\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert any(code.startswith("FORBIDDEN_IMPORT:importlib") for code in result.reason_codes)


def test_forbidden_importlib_alias_usage(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_importlib_alias",
        "import importlib as il\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    il.import_module('os')\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert any(
        code.startswith("FORBIDDEN_IMPORT:importlib")
        or code.startswith("FORBIDDEN_ATTRIBUTE:importlib.import_module")
        for code in result.reason_codes
    )


def test_forbidden_dunder_import_call(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_import_call",
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    __import__('os')\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert any(code.startswith("FORBIDDEN_CALL:__import__") for code in result.reason_codes)


def test_dunder_import_then_system_call_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_import_system",
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    __import__('os').system('echo hi')\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert any(code.startswith("FORBIDDEN_CALL:__import__") for code in result.reason_codes)


def test_import_function_alias_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_import_alias",
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    f = __import__\n    f('os')\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert any(code.startswith("FORBIDDEN_CALL:__import__") for code in result.reason_codes)


def test_getattr_dunder_import_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_getattr_import",
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    getattr(__builtins__, '__import__')('os')\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert any(
        code.startswith("FORBIDDEN_CALL:getattr(__builtins__)") or code.startswith("AST_UNCERTAIN")
        for code in result.reason_codes
    )


def test_getattr_builtins_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_getattr",
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    getattr(__builtins__, 'eval')('1+1')\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert any("getattr(__builtins__)" in code for code in result.reason_codes)


def test_getattr_builtins_open_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_getattr_open",
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    getattr(__builtins__, 'open')('x', 'w')\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert any("getattr(__builtins__)" in code for code in result.reason_codes)


def test_globals_builtins_open_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_globals",
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    globals()['__builtins__']['open']('x')\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert any(code.startswith("FORBIDDEN_CALL:globals") for code in result.reason_codes)


def test_builtins_open_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_builtins_open",
        "import builtins\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    builtins.open('x', 'w')\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert any(
        code.startswith("FORBIDDEN_IMPORT:builtins")
        or code.startswith("FORBIDDEN_ATTRIBUTE:builtins.open")
        for code in result.reason_codes
    )


def test_builtins_open_from_import_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_builtins_from",
        "from builtins import open as o\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    o('x', 'w')\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert any(
        code.startswith("FORBIDDEN_IMPORT:builtins")
        or code.startswith("FORBIDDEN_CALL:builtins.open")
        for code in result.reason_codes
    )


def test_from_os_system_alias_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_os_alias",
        "from os import system as s\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    s('echo hi')\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert any(code.startswith("FORBIDDEN_CALL:os.system") for code in result.reason_codes)


def test_import_os_alias_attribute_call_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_os_attr",
        "import os as o\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    o.system('echo hi')\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert any(code.startswith("FORBIDDEN_ATTRIBUTE:os.system") for code in result.reason_codes)


def test_path_open_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_path_open",
        "from pathlib import Path\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    Path('x').open('w')\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert any(
        code.startswith("FORBIDDEN_IMPORT:pathlib") or code.startswith("FORBIDDEN_CALL:Path.open")
        for code in result.reason_codes
    )


def test_path_write_text_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_path_write",
        "from pathlib import Path\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    Path('x').write_text('hi')\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert any(
        code.startswith("FORBIDDEN_IMPORT:pathlib") or code.startswith("FORBIDDEN_CALL:Path.open")
        for code in result.reason_codes
    )


def test_path_instance_write_text_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_path_instance",
        "from pathlib import Path\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    p = Path('x')\n    p.write_text('hi')\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert any(
        code.startswith("FORBIDDEN_IMPORT:pathlib")
        or code.startswith("FORBIDDEN_ATTRIBUTE:pathlib.Path.write_text")
        for code in result.reason_codes
    )


def test_ast_uncertain_on_unresolved_call(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_uncertain",
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    (lambda x: x)(1)\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert "AST_UNCERTAIN" in result.reason_codes


def test_datetime_now_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_datetime",
        "from datetime import datetime\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    datetime.now()\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert any(
        code.startswith("FORBIDDEN_IMPORT:datetime")
        or code.startswith("NON_DETERMINISTIC_API:datetime")
        for code in result.reason_codes
    )


def test_uuid_uuid4_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_uuid",
        "import uuid\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    uuid.uuid4()\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert any(code.startswith("FORBIDDEN_IMPORT:uuid") for code in result.reason_codes)


def test_import_allowlist_blocks_unapproved_modules(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_json",
        "import json\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert any(code.startswith("FORBIDDEN_IMPORT:json") for code in result.reason_codes)


def test_monkey_patching_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_patch",
        "import math\n\n"
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n"
        "    math.sin = lambda x: x\n"
        "    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert "MONKEY_PATCH" in result.reason_codes


def test_setattr_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_setattr",
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n"
        "    setattr(object(), 'x', 1)\n"
        "    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert any(code.startswith("FORBIDDEN_CALL:setattr") for code in result.reason_codes)


def test_delattr_is_invalid(tmp_path: Path) -> None:
    result = _validate_indicator(
        tmp_path,
        "unsafe_delattr",
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n"
        "    delattr(object(), 'x')\n"
        "    return {'value': 1}\n",
    )
    assert result.status == "INVALID"
    assert any(code.startswith("FORBIDDEN_CALL:delattr") for code in result.reason_codes)
