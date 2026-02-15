from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

PIDFILE_NAME = ".pids.json"
PORT_CLOSE_TIMEOUT_S = 20


def _log(message: str) -> None:
    print(message, flush=True)


def _process_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"preexec_fn": os.setsid}


def _port_in_use(family: int, address: str, port: int) -> bool:
    try:
        sock = socket.socket(family, socket.SOCK_STREAM)
    except OSError:
        return False
    with sock:
        sock.settimeout(0.2)
        return sock.connect_ex((address, port)) == 0


def _can_bind(family: int, address: str, port: int) -> bool:
    try:
        sock = socket.socket(family, socket.SOCK_STREAM)
    except OSError:
        return True
    with sock:
        try:
            sock.bind((address, port))
            return True
        except OSError:
            return False


def is_port_free(port: int) -> bool:
    if _port_in_use(socket.AF_INET, "127.0.0.1", port):
        return False
    if _port_in_use(socket.AF_INET6, "::1", port):
        return False
    return _can_bind(socket.AF_INET, "127.0.0.1", port) and _can_bind(socket.AF_INET6, "::1", port)


def pick_free_port(exclude: set[int] | None = None) -> int:
    excluded = exclude or set()
    for _ in range(50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        if port in excluded:
            continue
        if is_port_free(port):
            return port
    raise RuntimeError("Unable to pick a free port")


def pick_two_free_ports() -> tuple[int, int]:
    api_port = pick_free_port()
    ui_port = pick_free_port({api_port})
    return api_port, ui_port


def start_process(cmd: list[str], cwd: Path, env: dict[str, str], label: str) -> subprocess.Popen:
    _log(f"Command ({label}): {cmd}")
    return subprocess.Popen(cmd, cwd=str(cwd), env=env, **_process_kwargs())


def build_taskkill_command(pid: int) -> list[str]:
    return ["taskkill", "/PID", str(pid), "/T", "/F"]


def kill_pid_tree(pid: int, label: str, *, timeout_s: float = 10.0) -> None:
    if os.name == "nt":
        subprocess.run(
            build_taskkill_command(pid),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.2)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def kill_process_tree(
    proc: subprocess.Popen | None, label: str, *, timeout_s: float = 10.0
) -> None:
    if proc is None:
        return
    if proc.poll() is not None:
        return
    kill_pid_tree(proc.pid, label, timeout_s=timeout_s)


def wait_port_free(port: int, timeout_s: float = PORT_CLOSE_TIMEOUT_S) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if is_port_free(port):
            return True
        time.sleep(0.2)
    return False


def wait_http_200(url: str, timeout_s: float, expect_text: str | None = None) -> None:
    start = time.monotonic()
    while True:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                body = response.read().decode("utf-8", errors="ignore")
                if expect_text and expect_text not in body:
                    raise ValueError("expected text missing")
                return
        except (urllib.error.URLError, ValueError, TimeoutError):
            if time.monotonic() - start > timeout_s:
                raise TimeoutError(f"Timed out waiting for {url}")
            time.sleep(0.5)


def pidfile_path(repo_root: Path) -> Path:
    return repo_root / ".runs" / PIDFILE_NAME


def write_pidfile(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def read_pidfile(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _load_windows_processes() -> list[dict[str, str]]:
    cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "Get-CimInstance Win32_Process "
            "| Select-Object ProcessId,CommandLine,ExecutablePath "
            "| ConvertTo-Json -Compress"
        ),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    raw = (proc.stdout or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    processes = []
    for item in data:
        processes.append(
            {
                "pid": str(item.get("ProcessId", "")),
                "command": item.get("CommandLine", "") or "",
                "exe": item.get("ExecutablePath", "") or "",
            }
        )
    return processes


def _load_posix_processes() -> list[dict[str, str]]:
    proc = subprocess.run(
        ["ps", "-A", "-o", "pid=,command="],
        capture_output=True,
        text=True,
        check=False,
    )
    output = proc.stdout or ""
    processes = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if not parts:
            continue
        pid = parts[0]
        command = parts[1] if len(parts) > 1 else ""
        processes.append({"pid": pid, "command": command, "exe": ""})
    return processes


def list_processes() -> list[dict[str, str]]:
    if os.name == "nt":
        return _load_windows_processes()
    return _load_posix_processes()


def _normalized_path(path: Path) -> str:
    return str(path).replace("\\", "/").lower()


def is_buff_api_process(proc: dict[str, str], repo_root: Path) -> bool:
    cmd = (proc.get("command") or "").lower()
    repo = _normalized_path(repo_root)
    return "uvicorn" in cmd and "apps.api.main:app" in cmd and repo in cmd


def is_buff_next_process(proc: dict[str, str], repo_root: Path) -> bool:
    cmd = (proc.get("command") or "").lower()
    repo = _normalized_path(repo_root)
    if repo not in cmd:
        return False
    if "apps/web" not in cmd and "apps\\web" not in cmd:
        return False
    return ("next" in cmd and "dev" in cmd) or ("npm" in cmd and "run" in cmd and "dev" in cmd)


def buff_next_running(repo_root: Path) -> bool:
    for proc in list_processes():
        if is_buff_next_process(proc, repo_root):
            return True
    return False


def clear_next_dev_lock(repo_root: Path) -> None:
    lock_path = repo_root / "apps" / "web" / ".next" / "dev" / "lock"
    if not lock_path.exists():
        return
    if buff_next_running(repo_root):
        _log("WARN: next dev appears to be running; skipping lock removal.")
        return
    try:
        lock_path.unlink()
        _log("Removed stale Next.js dev lock.")
    except OSError as exc:
        _log(f"WARN: failed to remove Next.js dev lock: {exc}")
