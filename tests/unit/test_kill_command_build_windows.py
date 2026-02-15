from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest


def _load_orchestrator():
    path = Path(__file__).resolve().parents[2] / "scripts" / "_orchestrator.py"
    spec = importlib.util.spec_from_file_location("orchestrator", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(os.name != "nt", reason="Windows taskkill command")
def test_taskkill_command_build() -> None:
    orchestrator = _load_orchestrator()
    assert orchestrator.build_taskkill_command(42) == ["taskkill", "/PID", "42", "/T", "/F"]
