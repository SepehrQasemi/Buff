from __future__ import annotations

from importlib import import_module
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

CANONICAL_SURFACE = "risk.veto"
CANONICAL_CONTRACTS = "risk.contracts"

TYPE_SYMBOLS = ("RiskInputs", "RiskConfig", "RiskDecision", "RiskState")
IMPORT_FROM_RISK_TYPES = re.compile(r"^\s*from\s+risk\.types\s+import\b", re.MULTILINE)
IMPORT_RISK_TYPES = re.compile(r"^\s*import\s+risk\.types\b", re.MULTILINE)


def test_s4_canonical_surface_is_importable() -> None:
    surface = import_module(CANONICAL_SURFACE)
    contracts = import_module(CANONICAL_CONTRACTS)

    for symbol in (*TYPE_SYMBOLS, "risk_veto"):
        assert hasattr(surface, symbol), f"{CANONICAL_SURFACE} missing export: {symbol}"
    for symbol in TYPE_SYMBOLS:
        assert getattr(surface, symbol) is getattr(contracts, symbol), (
            f"{CANONICAL_SURFACE}.{symbol} must resolve to {CANONICAL_CONTRACTS}.{symbol}"
        )

    assert callable(surface.risk_veto)


def test_s4_state_machine_type_aliases_stay_canonical() -> None:
    contracts = import_module(CANONICAL_CONTRACTS)
    state_machine = import_module("risk.state_machine")

    for symbol in ("RiskConfig", "RiskDecision", "RiskState"):
        assert hasattr(state_machine, symbol), f"risk.state_machine missing: {symbol}"
        assert getattr(state_machine, symbol) is getattr(contracts, symbol), (
            f"risk.state_machine.{symbol} must alias {CANONICAL_CONTRACTS}.{symbol}"
        )


def test_s4_no_risk_types_imports_in_runtime_or_tests() -> None:
    violations: list[str] = []
    for root in ("src", "apps", "tests"):
        root_path = Path(root)
        if not root_path.exists():
            continue
        for path in root_path.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if IMPORT_FROM_RISK_TYPES.search(text) or IMPORT_RISK_TYPES.search(text):
                violations.append(path.as_posix())

    assert not violations, (
        f"risk.types imports are forbidden; replace with {CANONICAL_CONTRACTS}: "
        f"{sorted(violations)}"
    )
