from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_API_PORT = 8000
DEFAULT_UI_PORT = 3000
API_PORT_RANGE = (8000, 8010)
UI_PORT_RANGE = (3000, 3010)
UI_READY_PATH = "/runs/new"


def _log(message: str) -> None:
    print(message, flush=True)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _with_pythonpath(env: dict[str, str], repo_root: Path) -> dict[str, str]:
    updated = dict(env)
    src_path = repo_root / "src"
    existing = updated.get("PYTHONPATH")
    updated["PYTHONPATH"] = str(src_path) + (os.pathsep + existing if existing else "")
    return updated


def _process_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


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


def pick_port(preferred: int | None, port_range: tuple[int, int], label: str) -> int:
    if preferred is not None:
        if not is_port_free(preferred):
            raise RuntimeError(f"{label} port {preferred} is already in use.")
        return preferred
    start, end = port_range
    for port in range(start, end + 1):
        if is_port_free(port):
            if port != start:
                _log(f"{label} port {start} busy, using {port}.")
            return port
    raise RuntimeError(f"No free {label} port available in range {start}-{end}.")


def _wait_for_http(url: str, expect_text: str | None, timeout: float) -> None:
    start = time.monotonic()
    while True:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                body = response.read().decode("utf-8", errors="ignore")
                if expect_text and expect_text not in body:
                    raise ValueError("expected text missing")
                return
        except (urllib.error.URLError, ValueError, TimeoutError):
            if time.monotonic() - start > timeout:
                raise TimeoutError(f"Timed out waiting for {url}")
            time.sleep(0.5)


def _next_dev_running() -> bool:
    try:
        if os.name == "nt":
            proc = subprocess.run(
                ["wmic", "process", "get", "CommandLine"],
                capture_output=True,
                text=True,
                check=False,
            )
            output = proc.stdout or ""
        else:
            proc = subprocess.run(
                ["ps", "-ax", "-o", "command="],
                capture_output=True,
                text=True,
                check=False,
            )
            output = proc.stdout or ""
    except Exception:
        return False

    for line in output.splitlines():
        lowered = line.lower()
        if "next" in lowered and "dev" in lowered:
            return True
    return False


def _clear_next_dev_lock(repo_root: Path) -> None:
    lock_path = repo_root / "apps" / "web" / ".next" / "dev" / "lock"
    if not lock_path.exists():
        return
    if _next_dev_running():
        _log("WARN: next dev appears to be running; skipping lock removal.")
        return
    try:
        lock_path.unlink()
        _log("Removed stale Next.js dev lock.")
    except OSError as exc:
        _log(f"WARN: failed to remove Next.js dev lock: {exc}")


def _ensure_uvicorn_available() -> None:
    try:
        import uvicorn  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "uvicorn is not installed. Install dependencies with "
            '`python -m pip install -e ".[dev]"`.'
        ) from exc


def _ensure_node_available(repo_root: Path) -> str:
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        raise RuntimeError("npm not found on PATH. Install Node.js (includes npm).")

    web_root = repo_root / "apps" / "web"
    next_cmd = web_root / "node_modules" / ".bin" / ("next.cmd" if os.name == "nt" else "next")
    next_js = web_root / "node_modules" / "next" / "dist" / "bin" / "next"
    if not next_cmd.exists() and not next_js.exists():
        raise RuntimeError("UI dependencies missing. Run `cd apps/web` then `npm install`.")

    return npm


def _resolve_runs_root(repo_root: Path) -> Path:
    raw = os.environ.get("RUNS_ROOT")
    if raw:
        runs_root = Path(raw).expanduser().resolve()
        if not runs_root.is_relative_to(repo_root):
            raise RuntimeError(
                "RUNS_ROOT must be inside the repo for file uploads. "
                "Unset RUNS_ROOT to use the default .runs directory."
            )
    else:
        runs_root = (repo_root / ".runs").resolve()
    runs_root.mkdir(parents=True, exist_ok=True)
    return runs_root


def main() -> int:
    repo_root = _repo_root()

    try:
        runs_root = _resolve_runs_root(repo_root)
        _ensure_uvicorn_available()
        npm = _ensure_node_available(repo_root)
    except RuntimeError as exc:
        _log(f"ERROR: {exc}")
        return 1

    api_port_env = os.environ.get("API_PORT")
    ui_port_env = os.environ.get("UI_PORT")
    api_port = pick_port(
        int(api_port_env) if api_port_env else None,
        API_PORT_RANGE,
        "API",
    )
    ui_port = pick_port(
        int(ui_port_env) if ui_port_env else None,
        UI_PORT_RANGE,
        "UI",
    )

    _clear_next_dev_lock(repo_root)

    api_env = _with_pythonpath(os.environ.copy(), repo_root)
    api_env["RUNS_ROOT"] = str(runs_root)
    api_env["DEMO_MODE"] = "0"

    api_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "apps.api.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(api_port),
        "--reload",
    ]
    _log(f"Starting API on http://127.0.0.1:{api_port} (RUNS_ROOT={runs_root})")
    api_proc = subprocess.Popen(
        api_cmd,
        cwd=str(repo_root),
        env=api_env,
        **_process_kwargs(),
    )

    ui_env = os.environ.copy()
    ui_env["NEXT_PUBLIC_API_BASE"] = f"http://127.0.0.1:{api_port}/api/v1"
    ui_cmd = [npm, "run", "dev", "--", "--port", str(ui_port)]
    _log(f"Starting UI on http://127.0.0.1:{ui_port}")
    ui_proc = subprocess.Popen(
        ui_cmd,
        cwd=str(repo_root / "apps" / "web"),
        env=ui_env,
        **_process_kwargs(),
    )

    try:
        _wait_for_http(f"http://127.0.0.1:{api_port}/api/v1/health", "ok", timeout=60)
        _wait_for_http(f"http://127.0.0.1:{ui_port}{UI_READY_PATH}", None, timeout=120)
        _log("Dev servers ready.")
        _log(f"Open http://localhost:{ui_port}/runs/new")
        _log("Press Ctrl+C to stop.")
        ui_proc.wait()
    except KeyboardInterrupt:
        _log("Stopping dev servers...")
    except Exception as exc:
        _log(f"ERROR: {exc}")
        return 1
    finally:
        for proc, label in ((ui_proc, "UI"), (api_proc, "API")):
            if proc.poll() is None:
                _log(f"Stopping {label}...")
                try:
                    proc.terminate()
                except Exception:
                    pass
        for proc in (ui_proc, api_proc):
            try:
                proc.wait(timeout=10)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
