from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_dev_start_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "dev_start.py"
    spec = importlib.util.spec_from_file_location("dev_start", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_format_port_in_use_error_includes_hint() -> None:
    dev_start = _load_dev_start_module()
    message = dev_start._format_port_in_use_error("API", 8001)
    assert (
        message == "ERROR: API port 8001 is already in use. "
        "Choose a free port or stop the process using it. "
        "Set API_PORT to override."
    )
    assert "\n" not in message
