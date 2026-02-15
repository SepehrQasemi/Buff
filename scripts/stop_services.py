from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _orchestrator import (  # noqa: E402
    kill_pid_tree,
    list_processes,
    pidfile_path,
    read_pidfile,
)

PORT_PATTERN = re.compile(r"--port(?:=|\s+)(\d+)\b")


def _log(message: str) -> None:
    print(message, flush=True)


def _normalize(value: str) -> str:
    return value.lower()


def _cmd_has_port(cmd: str, port: int) -> bool:
    return re.search(rf"--port(?:=|\s+){port}\b", cmd) is not None


def _extract_port(cmd: str) -> int | None:
    match = PORT_PATTERN.search(cmd)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def get_process_info(pid: int) -> dict[str, str] | None:
    if os.name == "nt":
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                f'Get-CimInstance Win32_Process -Filter "ProcessId={pid}" '
                "| Select ExecutablePath,CommandLine | ConvertTo-Json -Compress"
            ),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        raw = (result.stdout or "").strip()
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(data, list):
            data = data[0] if data else {}
        return {
            "exe": data.get("ExecutablePath", "") or "",
            "cmd": data.get("CommandLine", "") or "",
        }

    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        capture_output=True,
        text=True,
        check=False,
    )
    cmdline = (result.stdout or "").strip()
    if not cmdline:
        return None
    return {"exe": "", "cmd": cmdline}


def is_valid_api(cmd: str, port: int) -> bool:
    lowered = _normalize(cmd)
    return "uvicorn" in lowered and "apps.api.main:app" in lowered and _cmd_has_port(lowered, port)


def is_valid_ui(cmd: str, port: int) -> bool:
    lowered = _normalize(cmd)
    signature = ("run dev" in lowered) or ("next dev" in lowered)
    return signature and _cmd_has_port(lowered, port)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    pid_path = pidfile_path(repo_root)
    killed: list[str] = []
    refused = False

    if pid_path.exists():
        data = read_pidfile(pid_path) or {}
        for label in ("api", "ui"):
            entry = data.get(label, {})
            pid = entry.get("pid")
            port = entry.get("port")
            if not pid or not port:
                continue
            try:
                pid_int = int(pid)
                port_int = int(port)
            except (TypeError, ValueError):
                refused = True
                _log(f"REFUSING to stop PID {pid}: invalid pid/port in pidfile.")
                continue

            info = get_process_info(pid_int)
            if info is None:
                _log(f"PID {pid_int} EXE=<none> CMD=<none>")
                continue
            cmd = info.get("cmd", "")
            exe = info.get("exe", "")
            _log(f"PID {pid_int} EXE={exe} CMD={cmd}")

            valid = is_valid_api(cmd, port_int) if label == "api" else is_valid_ui(cmd, port_int)
            if not valid:
                _log(
                    f"REFUSING to stop PID {pid_int}: does not match Buff signature for port {port_int}."
                )
                refused = True
                continue
            kill_pid_tree(pid_int, label.upper())
            killed.append(f"{label}:{pid_int}")

        if refused:
            return 2
        pid_path.unlink(missing_ok=True)
    else:
        repo_norm = str(repo_root).replace("\\", "/").lower()
        for proc in list_processes():
            cmd = proc.get("command", "") or ""
            exe = proc.get("exe", "") or ""
            pid_raw = proc.get("pid", "") or ""
            try:
                pid_int = int(pid_raw)
            except (TypeError, ValueError):
                continue

            cmd_lower = _normalize(cmd)
            is_api_sig = "uvicorn" in cmd_lower and "apps.api.main:app" in cmd_lower
            is_ui_sig = ("next dev" in cmd_lower) or ("run dev" in cmd_lower)
            if not (is_api_sig or is_ui_sig):
                continue

            _log(f"PID {pid_int} EXE={exe} CMD={cmd}")
            port = _extract_port(cmd_lower)
            if port is not None:
                valid = is_valid_api(cmd_lower, port) or is_valid_ui(cmd_lower, port)
            else:
                valid = repo_norm in cmd_lower and (is_api_sig or is_ui_sig)

            if not valid:
                _log(f"REFUSING to stop PID {pid_int}: does not match Buff signature.")
                continue

            kill_pid_tree(pid_int, "API" if is_api_sig else "UI")
            killed.append(f"pid:{pid_int}")

    if killed:
        _log("Stopped Buff services: " + ", ".join(killed))
    else:
        _log("No Buff services found to stop.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
