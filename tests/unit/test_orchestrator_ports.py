from __future__ import annotations

import importlib.util
import socket
from pathlib import Path


def _load_orchestrator():
    path = Path(__file__).resolve().parents[2] / "scripts" / "_orchestrator.py"
    spec = importlib.util.spec_from_file_location("orchestrator", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pick_free_port_bindable() -> None:
    orchestrator = _load_orchestrator()
    port = orchestrator.pick_free_port()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
    finally:
        sock.close()
