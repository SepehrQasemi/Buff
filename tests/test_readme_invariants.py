from __future__ import annotations

from pathlib import Path


def test_readme_invariants_section_present() -> None:
    text = Path("README.md").read_text(encoding="utf-8")
    lowered = text.casefold()
    assert "invariants & non-goals" in lowered
    assert "deterministic" in lowered
    assert "non-goals" in lowered
    assert "no prediction" in lowered
