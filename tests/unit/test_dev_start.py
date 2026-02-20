from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


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


def test_select_ports_defaults_ui_to_3000(monkeypatch: pytest.MonkeyPatch) -> None:
    dev_start = _load_dev_start_module()
    monkeypatch.setattr(dev_start, "is_port_free", lambda port: True)

    seen_excludes: list[set[int]] = []

    def _fake_pick_free_port(exclude=None):
        seen_excludes.append(set(exclude or set()))
        return 8001

    monkeypatch.setattr(dev_start, "pick_free_port", _fake_pick_free_port)
    api_port, ui_port = dev_start._select_ports(None, None)

    assert (api_port, ui_port) == (8001, 3000)
    assert seen_excludes == [{3000}]


def test_select_ports_falls_back_when_3000_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev_start = _load_dev_start_module()
    monkeypatch.setattr(dev_start, "is_port_free", lambda port: port != 3000)

    picks = [13000, 8001]

    def _fake_pick_free_port(exclude=None):
        _ = exclude
        return picks.pop(0)

    monkeypatch.setattr(dev_start, "pick_free_port", _fake_pick_free_port)
    api_port, ui_port = dev_start._select_ports(None, None)

    assert (api_port, ui_port) == (8001, 13000)


def test_main_passes_ui_port_to_api_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dev_start = _load_dev_start_module()
    monkeypatch.setattr(sys, "argv", ["dev_start.py", "--no-reload"])
    monkeypatch.setattr(dev_start, "_resolve_runs_root", lambda _repo_root: tmp_path / ".runs")
    monkeypatch.setattr(dev_start, "_ensure_uvicorn_available", lambda: None)
    monkeypatch.setattr(dev_start, "_ensure_node_available", lambda _repo_root: "npm")
    monkeypatch.setattr(dev_start, "_select_ports", lambda _api, _ui: (8100, 13000))
    monkeypatch.setattr(dev_start, "clear_next_dev_lock", lambda _repo_root: None)
    monkeypatch.setattr(dev_start, "wait_http_200", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dev_start, "wait_port_free", lambda _port: True)
    monkeypatch.setattr(dev_start, "kill_process_tree", lambda _proc, _label: None)
    monkeypatch.setattr(dev_start, "pidfile_path", lambda _repo_root: tmp_path / ".pids.json")
    monkeypatch.setattr(dev_start, "write_pidfile", lambda _path, _payload: None)

    captured_env: dict[str, str] = {}

    class _FakeProc:
        def __init__(self, pid: int) -> None:
            self.pid = pid

        def poll(self) -> None:
            return None

        def wait(self) -> int:
            return 0

    def _fake_start_process(cmd, cwd, env, label):
        _ = (cwd, label)
        if "uvicorn" in cmd:
            captured_env.update(env)
            return _FakeProc(101)
        return _FakeProc(202)

    monkeypatch.setattr(dev_start, "start_process", _fake_start_process)
    exit_code = dev_start.main()

    assert exit_code == 0
    assert captured_env["API_PORT"] == "8100"
    assert captured_env[dev_start.DEV_UI_PORT_ENV] == "13000"
