from __future__ import annotations

from strategies.registry import build_engines, get_profiles


def select_strategy(*, market_state: dict, risk_state: str, timeframe: str) -> dict:
    risk_state_norm = risk_state.upper()
    reasons: list[str] = []

    if risk_state_norm == "RED":
        return {
            "strategy_id": "NONE",
            "engine_id": None,
            "risk_state": risk_state_norm,
            "timeframe": timeframe,
            "reason": ["RISK_VETO:RED"],
        }

    engines = build_engines()
    profiles = get_profiles()

    if risk_state_norm == "YELLOW":
        profiles = [profile for profile in profiles if profile.conservative]
        reasons.append("RISK_LIMIT:YELLOW")

    selected = None
    for profile in profiles:
        ok_profile, profile_reasons = profile.is_profile_applicable(market_state=market_state)
        if not ok_profile:
            continue

        engine = engines.get(profile.engine_id)
        if engine is None:
            continue

        ok_engine, engine_reasons = engine.is_applicable(
            market_state=market_state, timeframe=timeframe
        )
        if not ok_engine:
            continue

        selected = {
            "strategy_id": profile.strategy_id,
            "engine_id": profile.engine_id,
            "risk_state": risk_state_norm,
            "timeframe": timeframe,
            "reason": reasons + profile_reasons + engine_reasons + [f"SELECTED:{profile.strategy_id}"],
        }
        break

    if selected is None:
        return {
            "strategy_id": "NONE",
            "engine_id": None,
            "risk_state": risk_state_norm,
            "timeframe": timeframe,
            "reason": reasons + ["NO_APPLICABLE_STRATEGY"],
        }

    return selected
