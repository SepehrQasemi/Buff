from __future__ import annotations

import re

FORBIDDEN_PATTERNS: dict[str, re.Pattern[str]] = {
    # Instruction-only lexical filter labels; this does not execute anything.
    "trade_intent": re.compile(r"\b(place|submit|send)\s+order(s)?\b"),
    "execute_trade": re.compile(r"\bexecute\s+(trade|order)(s)?\b"),
    "arm_control_plane": re.compile(r"\barm\b.*\b(control|live)\b"),
    "broker_action": re.compile(r"\bbroker\b.*\b(order|trade|execute)\b"),
    "go_live": re.compile(r"\bgo\s+live\b|\blive\s+trading\b"),
}


class SafetyGuardError(ValueError):
    """Raised when a request violates read-only or execution safety rules."""


def detect_forbidden(message: str) -> str | None:
    text = (message or "").lower()
    for label, pattern in FORBIDDEN_PATTERNS.items():
        if pattern.search(text):
            return label
    return None


def enforce_read_only(message: str) -> None:
    reason = detect_forbidden(message)
    if reason:
        raise SafetyGuardError(f"forbidden_intent:{reason}")
