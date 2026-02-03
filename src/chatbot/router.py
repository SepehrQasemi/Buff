from __future__ import annotations

from typing import Iterable

INTENTS = ("reporting", "auditing", "teaching")


def route_intent(message: str, intent_hint: str | None = None) -> str:
    if intent_hint and intent_hint in INTENTS:
        return intent_hint

    text = (message or "").lower()
    keyword_map: dict[str, Iterable[str]] = {
        "auditing": (
            "audit",
            "compliance",
            "trace",
            "decision record",
            "replay",
            "verification",
        ),
        "teaching": ("teach", "explain", "how to", "what is", "guide", "help"),
        "reporting": ("report", "summary", "daily", "status", "metrics"),
    }

    for intent, keywords in keyword_map.items():
        if any(keyword in text for keyword in keywords):
            return intent

    return "reporting"
