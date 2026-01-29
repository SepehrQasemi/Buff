from __future__ import annotations

import json
from pathlib import Path

RULES_PATH = Path("knowledge/market_state_rules.yaml")

TIMEFRAMES = [
    "1m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "1d",
    "1w",
    "2w",
    "1M",
    "3M",
    "6M",
    "1Y",
]

FORBIDDEN_WORDS = [
    "buy",
    "sell",
    "long",
    "short",
    "bullish",
    "bearish",
    "predict",
    "prediction",
    "forecast",
]

ALLOWED_INPUTS = {"open", "high", "low", "close", "volume"}

ALLOWED_OUTPUTS = {
    "trend": {"up", "down", "flat"},
    "momentum": {"positive", "neutral", "negative"},
    "volatility": {"low", "normal", "high", "undefined"},
    "regime": {"trending", "ranging", "transition"},
}

REQUIRED_FIELDS = {
    "id",
    "name",
    "category",
    "timeframe",
    "description",
    "inputs",
    "parameters",
    "formula",
    "output",
    "constraints",
    "references",
}


def _load_rules() -> list[dict]:
    text = RULES_PATH.read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise AssertionError("PyYAML required to load rules") from exc
        payload = yaml.safe_load(text)

    if isinstance(payload, dict) and "rules" in payload:
        payload = payload["rules"]

    assert isinstance(payload, list), "rules must be a list"
    return payload


def _rule_kind(rule_id: str) -> str:
    if ".trend." in rule_id:
        return "trend"
    if ".momentum." in rule_id:
        return "momentum"
    if ".volatility." in rule_id:
        return "volatility"
    if ".regime." in rule_id:
        return "regime"
    raise AssertionError(f"Unrecognized rule_id kind: {rule_id}")


def _text_contains_forbidden(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in FORBIDDEN_WORDS)


def test_rules_load_and_count() -> None:
    rules = _load_rules()
    assert rules, "rules must not be empty"
    assert len(rules) == 56


def test_rules_have_required_fields() -> None:
    rules = _load_rules()
    for rule in rules:
        assert isinstance(rule, dict)
        missing = REQUIRED_FIELDS - set(rule.keys())
        assert not missing, f"missing fields: {missing}"


def test_rule_ids_unique() -> None:
    rules = _load_rules()
    rule_ids = [rule["id"] for rule in rules]
    assert len(rule_ids) == len(set(rule_ids))


def test_timeframe_coverage() -> None:
    rules = _load_rules()
    by_tf: dict[str, list[str]] = {tf: [] for tf in TIMEFRAMES}
    for rule in rules:
        tf = rule["timeframe"]
        assert tf in by_tf
        by_tf[tf].append(_rule_kind(rule["id"]))

    for tf, kinds in by_tf.items():
        assert sorted(kinds) == ["momentum", "regime", "trend", "volatility"], tf


def test_forbidden_words_absent() -> None:
    rules = _load_rules()
    for rule in rules:
        text_fields = [
            rule.get("name", ""),
            rule.get("description", ""),
            rule.get("formula", ""),
            rule.get("constraints", ""),
        ]
        combined = " ".join(text_fields)
        assert not _text_contains_forbidden(combined)


def test_inputs_and_references_contract() -> None:
    rules = _load_rules()
    for rule in rules:
        inputs = rule["inputs"]
        assert isinstance(inputs, list)
        assert inputs, "inputs must not be empty"
        for value in inputs:
            assert isinstance(value, str)
            assert value in ALLOWED_INPUTS

        references = rule["references"]
        assert isinstance(references, list)
        assert references, "references must not be empty"


def test_output_enums() -> None:
    rules = _load_rules()
    for rule in rules:
        kind = _rule_kind(rule["id"])
        output = rule["output"]
        assert isinstance(output, dict)
        assert output.get("type") == "enum"
        values = output.get("values")
        assert isinstance(values, list)
        assert set(values) == ALLOWED_OUTPUTS[kind]
