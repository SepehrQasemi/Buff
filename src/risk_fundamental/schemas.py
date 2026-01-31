"""YAML loader and validation for fundamental risk rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_rules(path: str | Path) -> dict[str, Any]:
    rules_path = Path(path)
    raw = rules_path.read_text(encoding="utf-8-sig")
    try:
        import yaml  # type: ignore

        payload = yaml.safe_load(raw)
    except ModuleNotFoundError:
        payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("rules_yaml_not_mapping")
    validate_rules(payload)
    return payload


def validate_rules(payload: dict[str, Any]) -> None:
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        raise ValueError("rules_meta_missing")

    forbidden_terms = meta.get("forbidden_terms")
    if not isinstance(forbidden_terms, list) or not all(
        isinstance(t, str) for t in forbidden_terms
    ):
        raise ValueError("forbidden_terms_invalid")
    forbidden_terms_lower = [term.lower() for term in forbidden_terms]

    domains = payload.get("domains")
    if not isinstance(domains, list) or not all(isinstance(d, str) for d in domains):
        raise ValueError("domains_invalid")

    outputs = payload.get("outputs")
    if not isinstance(outputs, dict):
        raise ValueError("outputs_invalid")

    inputs_catalog = payload.get("inputs_catalog")
    if not isinstance(inputs_catalog, list):
        raise ValueError("inputs_catalog_invalid")

    catalog_keys: dict[str, dict[str, dict[str, Any]]] = {}
    for entry in inputs_catalog:
        if not isinstance(entry, dict):
            raise ValueError("inputs_catalog_entry_invalid")
        key = entry.get("key")
        domain = entry.get("domain")
        dtype = entry.get("dtype")
        if not isinstance(key, str) or not isinstance(domain, str) or not isinstance(dtype, str):
            raise ValueError("inputs_catalog_entry_missing_fields")
        if domain not in domains:
            raise ValueError(f"inputs_catalog_domain_unknown:{domain}")
        catalog_keys.setdefault(domain, {})[key] = entry

    _validate_forbidden_terms(forbidden_terms_lower, list(catalog_keys))

    rules = payload.get("rules")
    if not isinstance(rules, list):
        raise ValueError("rules_missing")

    aggregation = payload.get("aggregation")
    if not isinstance(aggregation, dict):
        raise ValueError("aggregation_missing")
    aggregation_rules = aggregation.get("rules")
    if not isinstance(aggregation_rules, list):
        raise ValueError("aggregation_rules_missing")

    seen_ids: set[str] = set()
    for rule in rules:
        _validate_rule(
            rule=rule,
            catalog_keys=catalog_keys,
            outputs=outputs,
            forbidden_terms_lower=forbidden_terms_lower,
            seen_ids=seen_ids,
            allow_extra_outputs=False,
        )

    for rule in aggregation_rules:
        _validate_aggregation_rule(
            rule=rule,
            outputs=outputs,
            forbidden_terms_lower=forbidden_terms_lower,
            seen_ids=seen_ids,
        )

    _validate_aggregation_completeness(aggregation_rules, outputs)


def _validate_rule(
    *,
    rule: dict[str, Any],
    catalog_keys: dict[str, dict[str, dict[str, Any]]],
    outputs: dict[str, Any],
    forbidden_terms_lower: list[str],
    seen_ids: set[str],
    allow_extra_outputs: bool,
) -> None:
    if not isinstance(rule, dict):
        raise ValueError("rule_invalid")

    rule_id = rule.get("id")
    name = rule.get("name")
    domain = rule.get("domain")
    inputs = rule.get("inputs")
    when = rule.get("when")
    then = rule.get("then")

    if not isinstance(rule_id, str) or not isinstance(name, str):
        raise ValueError("rule_missing_id_or_name")
    if rule_id in seen_ids:
        raise ValueError(f"duplicate_rule_id:{rule_id}")
    seen_ids.add(rule_id)

    if not isinstance(domain, str):
        raise ValueError(f"rule_missing_domain:{rule_id}")

    _validate_forbidden_terms(forbidden_terms_lower, [rule_id, name, domain])

    if not isinstance(inputs, list):
        raise ValueError(f"rule_inputs_invalid:{rule_id}")

    for key in inputs:
        if not isinstance(key, str):
            raise ValueError(f"rule_input_invalid:{rule_id}")
        _validate_forbidden_terms(forbidden_terms_lower, [key])
        if catalog_keys and key not in catalog_keys.get(domain, {}):
            raise ValueError(f"rule_input_unknown:{rule_id}:{key}")

    if not isinstance(when, dict):
        raise ValueError(f"rule_when_invalid:{rule_id}")
    _validate_when(when, rule_id)

    if not isinstance(then, dict) or "set" not in then:
        raise ValueError(f"rule_then_invalid:{rule_id}")
    outputs_set = then.get("set")
    if not isinstance(outputs_set, dict):
        raise ValueError(f"rule_then_set_invalid:{rule_id}")

    for out_key, out_value in outputs_set.items():
        if not isinstance(out_key, str):
            raise ValueError(f"rule_output_key_invalid:{rule_id}")
        _validate_forbidden_terms(forbidden_terms_lower, [out_key])
        if out_key in outputs:
            allowed_values = outputs[out_key]
            if not isinstance(allowed_values, list):
                raise ValueError(f"outputs_enum_invalid:{out_key}")
            if out_value not in allowed_values:
                raise ValueError(f"rule_output_value_invalid:{rule_id}:{out_key}")
        elif not allow_extra_outputs:
            raise ValueError(f"rule_output_unknown:{rule_id}:{out_key}")


def _validate_aggregation_rule(
    *,
    rule: dict[str, Any],
    outputs: dict[str, Any],
    forbidden_terms_lower: list[str],
    seen_ids: set[str],
) -> None:
    if not isinstance(rule, dict):
        raise ValueError("aggregation_rule_invalid")
    rule_id = rule.get("id")
    if not isinstance(rule_id, str):
        raise ValueError("aggregation_rule_missing_id")
    if rule_id in seen_ids:
        raise ValueError(f"duplicate_rule_id:{rule_id}")
    seen_ids.add(rule_id)
    _validate_forbidden_terms(forbidden_terms_lower, [rule_id])

    when = rule.get("when")
    if not isinstance(when, dict):
        raise ValueError(f"aggregation_when_invalid:{rule_id}")
    _validate_when(when, rule_id)

    then = rule.get("then")
    if not isinstance(then, dict) or "set" not in then:
        raise ValueError(f"aggregation_then_invalid:{rule_id}")
    outputs_set = then.get("set")
    if not isinstance(outputs_set, dict):
        raise ValueError(f"aggregation_then_set_invalid:{rule_id}")

    for out_key, out_value in outputs_set.items():
        if not isinstance(out_key, str):
            raise ValueError(f"aggregation_output_key_invalid:{rule_id}")
        _validate_forbidden_terms(forbidden_terms_lower, [out_key])
        if out_key in outputs:
            allowed_values = outputs[out_key]
            if not isinstance(allowed_values, list):
                raise ValueError(f"outputs_enum_invalid:{out_key}")
            if out_value not in allowed_values:
                raise ValueError(f"aggregation_output_value_invalid:{rule_id}:{out_key}")


def _validate_when(when: dict[str, Any], rule_id: str) -> None:
    if "all" in when:
        if not isinstance(when["all"], list):
            raise ValueError(f"rule_when_all_invalid:{rule_id}")
        _validate_predicates(when["all"], rule_id)
        return
    if "any" in when:
        if not isinstance(when["any"], list):
            raise ValueError(f"rule_when_any_invalid:{rule_id}")
        _validate_predicates(when["any"], rule_id)
        return
    raise ValueError(f"rule_when_missing_all_any:{rule_id}")


def _validate_predicates(predicates: list[Any], rule_id: str) -> None:
    if not predicates:
        raise ValueError(f"rule_predicates_empty:{rule_id}")
    for predicate in predicates:
        if not isinstance(predicate, dict) or len(predicate) != 1:
            raise ValueError(f"rule_predicate_invalid:{rule_id}")
        op, config = next(iter(predicate.items()))
        if op not in {"eq", "gte", "lte", "gte_abs_diff", "lte_abs_diff", "missing"}:
            raise ValueError(f"rule_operator_invalid:{rule_id}:{op}")
        if op in {"eq", "gte", "lte"}:
            if not isinstance(config, dict) or len(config) != 1:
                raise ValueError(f"rule_operator_config_invalid:{rule_id}:{op}")
        if op in {"gte_abs_diff", "lte_abs_diff"}:
            if not isinstance(config, dict):
                raise ValueError(f"rule_operator_config_invalid:{rule_id}:{op}")
            if not {"lhs", "rhs", "value"}.issubset(config):
                raise ValueError(f"rule_abs_diff_missing_fields:{rule_id}")
        if op == "missing":
            if not isinstance(config, (dict, str)):
                raise ValueError(f"rule_missing_config_invalid:{rule_id}")


def _validate_forbidden_terms(forbidden_terms_lower: list[str], values: list[str]) -> None:
    for value in values:
        lower = value.lower()
        for term in forbidden_terms_lower:
            if term in lower:
                raise ValueError(f"forbidden_term:{term}")


def _validate_aggregation_completeness(
    aggregation_rules: list[dict[str, Any]], outputs: dict[str, Any]
) -> None:
    desired_states = outputs.get("final_risk_state")
    if not isinstance(desired_states, list):
        raise ValueError("final_risk_state_enum_missing")

    covered: set[str] = set()
    for rule in aggregation_rules:
        then = rule.get("then", {})
        outputs_set = then.get("set", {}) if isinstance(then, dict) else {}
        final_state = outputs_set.get("final_risk_state")
        if isinstance(final_state, str):
            covered.add(final_state)
    missing = set(desired_states) - covered
    if missing:
        raise ValueError(f"aggregation_missing_states:{sorted(missing)}")
