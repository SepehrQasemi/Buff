"""Parser and validator for technical rules (M2 skeleton)."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import json

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal environments
    yaml = None


DEFAULT_REQUIRED_KEYS = {"id", "name", "inputs", "formula", "parameters", "references"}


def _load_yaml(path: Path) -> object:
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        return yaml.safe_load(text)
    return json.loads(text)


def _extract_rules(payload: object) -> list[dict]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and "rules" in payload:
        rules = payload["rules"]
        if rules is None:
            return []
        if isinstance(rules, list):
            return rules
    raise ValueError("technical_rules.yaml must be a list or a dict with 'rules' list.")


def _load_required_keys(schema_path: Path) -> set[str]:
    if not schema_path.exists():
        return set(DEFAULT_REQUIRED_KEYS)
    schema = _load_yaml(schema_path)
    if not isinstance(schema, dict):
        return set(DEFAULT_REQUIRED_KEYS)
    keys = schema.get("required_keys")
    if isinstance(keys, list) and keys:
        return set(keys)
    return set(DEFAULT_REQUIRED_KEYS)


def validate_rules(rules: Iterable[dict], required_keys: set[str]) -> None:
    for idx, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict):
            raise ValueError(f"Rule #{idx} must be a mapping.")
        missing = sorted(required_keys - set(rule.keys()))
        if missing:
            rule_id = rule.get("id", f"index:{idx}")
            raise ValueError(f"Rule {rule_id} missing keys: {missing}")


def load_and_validate(path: Path, schema_path: Path | None = None) -> list[dict]:
    payload = _load_yaml(path)
    rules = _extract_rules(payload)
    required_keys = _load_required_keys(schema_path or Path("knowledge/schema.yaml"))
    validate_rules(rules, required_keys)
    return rules


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate technical_rules.yaml schema.")
    parser.add_argument(
        "--path",
        type=str,
        required=True,
        help="Path to technical_rules.yaml",
    )
    parser.add_argument(
        "--schema",
        type=str,
        default="knowledge/schema.yaml",
        help="Path to schema.yaml",
    )
    args = parser.parse_args()
    load_and_validate(Path(args.path), Path(args.schema))
    print("OK")


if __name__ == "__main__":
    main()
