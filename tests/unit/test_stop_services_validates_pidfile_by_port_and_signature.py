from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_stop_services():
    path = Path(__file__).resolve().parents[2] / "scripts" / "stop_services.py"
    spec = importlib.util.spec_from_file_location("stop_services", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stop_services_validates_pidfile_by_port_and_signature(tmp_path: Path, monkeypatch) -> None:
    stop_services = _load_stop_services()
    pidfile = tmp_path / "pids.json"
    data = {
        "api": {"pid": 1111, "port": 5555},
        "ui": {"pid": 2222, "port": 6666},
    }
    pidfile.write_text(json.dumps(data), encoding="utf-8")

    monkeypatch.setattr(stop_services, "pidfile_path", lambda _root: pidfile)

    def fake_info(pid: int):
        if pid == 1111:
            return {
                "exe": "python",
                "cmd": "python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 5555",
            }
        if pid == 2222:
            return {
                "exe": "node",
                "cmd": "npm run dev -- --port 6666",
            }
        return None

    monkeypatch.setattr(stop_services, "get_process_info", fake_info)

    killed: list[int] = []

    def fake_kill(pid: int, label: str):
        killed.append(pid)

    monkeypatch.setattr(stop_services, "kill_pid_tree", fake_kill)

    code = stop_services.main()
    assert code == 0
    assert sorted(killed) == [1111, 2222]
    assert not pidfile.exists()
