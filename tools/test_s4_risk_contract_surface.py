from __future__ import annotations

from importlib import import_module
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

CANONICAL_SURFACE = "risk.veto"

# Canonical authoring modules used by the active gate path in risk.veto.
AUTHORITATIVE_DEFINERS: dict[str, str] = {
    "RiskInputs": "risk.contracts",
    "RiskConfig": "risk.state_machine",
    "RiskDecision": "risk.state_machine",
    "RiskState": "risk.state_machine",
    "risk_veto": "risk.veto",
}

SCANNED_DEFINER_MODULES = ("risk.contracts", "risk.state_machine", "risk.types")

# Explicitly declared duplicate definitions that are tolerated but non-authoritative.
ALLOWED_NON_AUTHORITATIVE_DEFINERS: dict[str, set[str]] = {
    "RiskInputs": {"risk.types"},
    "RiskConfig": {"risk.types"},
    "RiskDecision": {"risk.types"},
    "RiskState": {"risk.types"},
}


def _defined_here(module_name: str, symbol: str) -> bool:
    module = import_module(module_name)
    if not hasattr(module, symbol):
        return False
    value = getattr(module, symbol)
    return getattr(value, "__module__", None) == module_name


def _load_symbol(module_name: str, symbol: str) -> Any:
    module = import_module(module_name)
    assert hasattr(module, symbol), f"{module_name} missing symbol: {symbol}"
    return getattr(module, symbol)


def test_s4_canonical_surface_is_importable() -> None:
    surface = import_module(CANONICAL_SURFACE)

    for symbol in AUTHORITATIVE_DEFINERS:
        assert hasattr(surface, symbol), f"{CANONICAL_SURFACE} missing export: {symbol}"

    assert callable(surface.risk_veto)


def test_s4_canonical_surface_points_to_authoritative_symbols() -> None:
    surface = import_module(CANONICAL_SURFACE)

    for symbol, authoritative_module in AUTHORITATIVE_DEFINERS.items():
        assert getattr(surface, symbol) is _load_symbol(authoritative_module, symbol)


def test_s4_fragmentation_is_explicit_and_bounded() -> None:
    for symbol, authoritative_module in AUTHORITATIVE_DEFINERS.items():
        if symbol == "risk_veto":
            continue

        defining_modules = {
            module_name
            for module_name in SCANNED_DEFINER_MODULES
            if _defined_here(module_name, symbol)
        }
        assert authoritative_module in defining_modules, (
            f"authoritative definer missing for {symbol}: {authoritative_module}"
        )

        non_authoritative = defining_modules - {authoritative_module}
        unexpected = non_authoritative - ALLOWED_NON_AUTHORITATIVE_DEFINERS.get(symbol, set())
        assert not unexpected, (
            f"fragmented contract surface for {symbol}; unexpected definers: {sorted(unexpected)}"
        )
