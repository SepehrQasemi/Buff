from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_orchestrator():
    path = Path(__file__).resolve().parents[2] / "scripts" / "_orchestrator.py"
    spec = importlib.util.spec_from_file_location("orchestrator", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pidfile_roundtrip(tmp_path: Path) -> None:
    orchestrator = _load_orchestrator()
    data = {
        "api": {"pid": 123, "port": 9000},
        "ui": {"pid": 456, "port": 9001},
        "started_at": 1.23,
        "mode": "test",
    }
    path = tmp_path / "pids.json"
    orchestrator.write_pidfile(path, data)
    loaded = orchestrator.read_pidfile(path)
    assert loaded == data
