from __future__ import annotations

import ast
import re
from pathlib import Path

from src.plugins import validation as validation_module
from strategies.builtins import common as strategy_common


def _read_text_normalized(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AssertionError("Contract docs must be UTF-8 (optionally with BOM).") from exc
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n"))


def _extract_canonical_constants(path: Path) -> dict[str, set[str]]:
    text = _read_text_normalized(path)
    lines = text.split("\n")
    in_section = False
    in_fence = False
    block_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not in_section:
            if stripped.lower() == "## canonical contract constants":
                in_section = True
            continue
        if not in_fence:
            if stripped.startswith("```"):
                in_fence = True
            elif stripped:
                continue
            else:
                continue
        else:
            if stripped.startswith("```"):
                break
            block_lines.append(line)
    if not block_lines:
        raise AssertionError("Canonical contract constants block not found.")

    constants: dict[str, set[str]] = {}
    for line in block_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^([A-Z0-9_]+)\s*:\s*(\[.*\])\s*$", stripped)
        if not match:
            raise AssertionError(f"Invalid canonical line: {line!r}")
        key = match.group(1)
        value = ast.literal_eval(match.group(2))
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise AssertionError(f"Canonical values for {key} must be list[str].")
        constants[key] = set(value)
    return constants


def _extract_param_types_from_registry(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_validate_param_schema":
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Compare):
                    continue
                if not isinstance(inner.left, ast.Name) or inner.left.id != "param_type":
                    continue
                if not inner.ops or not isinstance(inner.ops[0], ast.NotIn):
                    continue
                if not inner.comparators or not isinstance(inner.comparators[0], ast.Set):
                    continue
                values = set()
                for elt in inner.comparators[0].elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        values.add(elt.value)
                if values:
                    return values
    raise AssertionError("param type set not found in strategies.registry")


def test_contract_constants_match_authoritative_sources() -> None:
    indicator_doc = Path("docs/INDICATOR_CONTRACT.md")
    constants = _extract_canonical_constants(indicator_doc)

    required_keys = {"ALLOWED_PARAM_TYPES", "ALLOWED_NAN_POLICIES", "ALLOWED_INTENTS"}
    missing = required_keys - set(constants)
    if missing:
        raise AssertionError(f"Missing canonical constants: {sorted(missing)}")

    assert constants["ALLOWED_PARAM_TYPES"] == validation_module.ALLOWED_PARAM_TYPES
    assert constants["ALLOWED_NAN_POLICIES"] == validation_module.ALLOWED_NAN_POLICIES
    assert constants["ALLOWED_INTENTS"] == validation_module.ALLOWED_INTENTS

    assert validation_module.ALLOWED_INTENTS == strategy_common.ALLOWED_INTENTS

    registry_types = _extract_param_types_from_registry(Path("src/strategies/registry.py"))
    assert validation_module.ALLOWED_PARAM_TYPES == registry_types
