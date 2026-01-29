from __future__ import annotations

from typing import TYPE_CHECKING

from strategies.registry import build_engines, get_profiles

if TYPE_CHECKING:  # pragma: no cover
    from audit.decision_records import DecisionRecordWriter


def select_strategy(
    *,
    market_state: dict,
    risk_state: str,
    timeframe: str,
    record_writer: "DecisionRecordWriter | None" = None,
) -> dict:
    risk_state_norm = risk_state.upper()
    reasons: list[str] = []

    if risk_state_norm == "RED":
        out = {
            "strategy_id": "NONE",
            "engine_id": None,
            "risk_state": risk_state_norm,
            "timeframe": timeframe,
            "reason": ["RISK_VETO:RED"],
        }
        if record_writer is not None:
            record_writer.append(
                timeframe=timeframe,
                risk_state=risk_state_norm,
                market_state=market_state,
                selection={
                    "strategy_id": out["strategy_id"],
                    "engine_id": out["engine_id"],
                    "reason": out["reason"],
                },
            )
        return out

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
        out = {
            "strategy_id": "NONE",
            "engine_id": None,
            "risk_state": risk_state_norm,
            "timeframe": timeframe,
            "reason": reasons + ["NO_APPLICABLE_STRATEGY"],
        }
        if record_writer is not None:
            record_writer.append(
                timeframe=timeframe,
                risk_state=risk_state_norm,
                market_state=market_state,
                selection={
                    "strategy_id": out["strategy_id"],
                    "engine_id": out["engine_id"],
                    "reason": out["reason"],
                },
            )
        return out

    if record_writer is not None:
        record_writer.append(
            timeframe=timeframe,
            risk_state=risk_state_norm,
            market_state=market_state,
            selection={
                "strategy_id": selected["strategy_id"],
                "engine_id": selected.get("engine_id"),
                "reason": selected["reason"],
            },
        )
    return selected
