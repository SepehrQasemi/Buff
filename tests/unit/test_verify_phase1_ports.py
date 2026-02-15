from __future__ import annotations

import socket
import pytest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_verify_phase1():
    repo_root = Path(__file__).resolve().parents[2]
    path = repo_root / "scripts" / "verify_phase1.py"
    spec = spec_from_file_location("verify_phase1", path)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_select_port_prefers_free() -> None:
    verify = _load_verify_phase1()
    preferred = _free_port()
    api_port, ui_port = verify._select_ports(preferred, None)
    assert api_port == preferred
    assert ui_port != preferred


def test_select_port_when_busy() -> None:
    verify = _load_verify_phase1()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    preferred = sock.getsockname()[1]
    try:
        with pytest.raises(RuntimeError, match="already in use"):
            verify._select_ports(preferred, None)
    finally:
        sock.close()


def test_env_override_precedence() -> None:
    verify = _load_verify_phase1()
    assert verify._parse_port("8123", "API") == 8123
