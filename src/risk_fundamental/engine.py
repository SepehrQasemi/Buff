"""Fundamental risk engine orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .contracts import (
    Evidence,
    FundamentalSnapshot,
    ensure_utc_timestamp,
    validate_snapshot_against_catalog,
)
from .rule_engine import evaluate_when
from .schemas import load_rules


@dataclass(frozen=True)
class FundamentalRiskDecision:
    timestamp: datetime
    macro_risk_state: str
    onchain_stress_level: str
    news_risk_flag: bool | str
    final_risk_state: str
    trade_permission: bool
    size_multiplier: float
    missing_inputs: list[str]
    evidence: list[Evidence]


class FundamentalRiskEngine:
    def __init__(self) -> None:
        self._rules: dict[str, Any] | None = None

    def load_rules(self, path: str | Path) -> None:
        self._rules = load_rules(path)

    def compute(self, snapshot: FundamentalSnapshot) -> FundamentalRiskDecision:
        if self._rules is None:
            raise ValueError("rules_not_loaded")

        snapshot_ts = ensure_utc_timestamp(snapshot.timestamp)
        inputs_catalog = self._rules["inputs_catalog"]
        missing_inputs, missing_critical = validate_snapshot_against_catalog(
            snapshot, inputs_catalog
        )

        states: dict[str, Any] = {
            "macro_risk_state": "unknown",
            "onchain_stress_level": "unknown",
            "news_risk_flag": "unknown",
        }
        matched_domains = {"macro": False, "onchain": False, "news": False}
        evidence: list[Evidence] = []

        for rule in self._rules["rules"]:
            domain = rule.get("domain")
            inputs = (
                snapshot.macro
                if domain == "macro"
                else (snapshot.onchain if domain == "onchain" else snapshot.news)
            )
            matched, reason = evaluate_when(rule.get("when", {}), inputs)
            inputs_used = {key: inputs.get(key) for key in rule.get("inputs", [])}
            evidence.append(
                Evidence(
                    rule_id=str(rule.get("id")),
                    domain=str(domain),
                    matched=matched,
                    severity=float(rule.get("severity", 0.0)),
                    inputs_used=inputs_used,
                    reason=reason,
                )
            )
            if matched:
                matched_domains[domain] = True
                for key, value in rule.get("then", {}).get("set", {}).items():
                    states[key] = _merge_state(states.get(key), key, value)

        _apply_domain_defaults(states, matched_domains, snapshot)

        final_state, trade_permission, size_multiplier = _aggregate(
            states, self._rules["aggregation"]
        )

        if missing_inputs:
            if final_state == "green":
                final_state = "yellow"
                trade_permission = True
                size_multiplier = min(size_multiplier, 0.35)
            evidence.append(
                Evidence(
                    rule_id="FAILSAFE_MISSING",
                    domain="system",
                    matched=True,
                    severity=1.0,
                    inputs_used={"missing_inputs": list(missing_inputs)},
                    reason="missing_inputs_present",
                )
            )

        if missing_critical and final_state == "green":
            final_state = "yellow"
            trade_permission = True
            size_multiplier = min(size_multiplier, 0.35)

        return FundamentalRiskDecision(
            timestamp=snapshot_ts,
            macro_risk_state=str(states["macro_risk_state"]),
            onchain_stress_level=str(states["onchain_stress_level"]),
            news_risk_flag=states["news_risk_flag"],
            final_risk_state=final_state,
            trade_permission=trade_permission,
            size_multiplier=float(size_multiplier),
            missing_inputs=list(missing_inputs),
            evidence=list(evidence),
        )


def _apply_domain_defaults(
    states: dict[str, Any],
    matched_domains: dict[str, bool],
    snapshot: FundamentalSnapshot,
) -> None:
    if _domain_has_data(snapshot.macro) and not matched_domains["macro"]:
        states["macro_risk_state"] = "low"
    if _domain_has_data(snapshot.onchain) and not matched_domains["onchain"]:
        states["onchain_stress_level"] = "normal"
    if _domain_has_data(snapshot.news) and not matched_domains["news"]:
        states["news_risk_flag"] = False


def _domain_has_data(values: dict[str, Any]) -> bool:
    return any(value is not None for value in values.values())


def _merge_state(current: Any, key: str, candidate: Any) -> Any:
    if current in (None, "unknown"):
        return candidate
    ordering = {
        "macro_risk_state": {"low": 0, "medium": 1, "high": 2},
        "onchain_stress_level": {"normal": 0, "elevated": 1, "extreme": 2},
        "news_risk_flag": {False: 0, True: 1},
    }
    if key not in ordering:
        return candidate
    current_rank = ordering[key].get(current, 0)
    candidate_rank = ordering[key].get(candidate, 0)
    return candidate if candidate_rank >= current_rank else current


def _aggregate(states: dict[str, Any], aggregation: dict[str, Any]) -> tuple[str, bool, float]:
    for rule in aggregation.get("rules", []):
        matched, _reason = evaluate_when(rule.get("when", {}), states)
        if matched:
            outputs = rule.get("then", {}).get("set", {})
            return (
                str(outputs.get("final_risk_state")),
                bool(outputs.get("trade_permission")),
                float(outputs.get("size_multiplier")),
            )
    return "yellow", True, 0.0
