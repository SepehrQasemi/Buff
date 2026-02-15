from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _orchestrator import (  # noqa: E402
    clear_next_dev_lock,
    is_port_free,
    kill_process_tree,
    pick_free_port,
    pick_two_free_ports,
    pidfile_path,
    start_process,
    wait_http_200,
    wait_port_free,
    write_pidfile,
)

UI_READY_PATH = "/runs/new"


def _log(message: str) -> None:
    print(message, flush=True)


def _fail(message: str) -> int:
    print(message, file=sys.stderr, flush=True)
    return 1


def _format_port_in_use_error(label: str, port: int) -> str:
    env_var = f"{label.upper()}_PORT"
    return (
        f"ERROR: {label} port {port} is already in use. "
        "Choose a free port or stop the process using it. "
        f"Set {env_var} to override."
    )


def _handle_port_error(label: str, preferred_raw: str | None, exc: RuntimeError) -> int:
    message = str(exc)
    env_var = f"{label.upper()}_PORT"
    if preferred_raw:
        try:
            preferred = int(preferred_raw)
        except ValueError:
            preferred = None
        if preferred is not None and "already in use" in message:
            return _fail(_format_port_in_use_error(label, preferred))
    return _fail(f"ERROR: {message} Set {env_var} to override.")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _with_pythonpath(env: dict[str, str], repo_root: Path) -> dict[str, str]:
    updated = dict(env)
    src_path = repo_root / "src"
    existing = updated.get("PYTHONPATH")
    updated["PYTHONPATH"] = str(src_path) + (os.pathsep + existing if existing else "")
    return updated


def _ensure_uvicorn_available() -> None:
    try:
        import uvicorn  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "uvicorn is not installed. Install dependencies with "
            '`python -m pip install -e ".[dev]"`. '
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


def _parse_port(raw: str | None, label: str) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        port = int(raw)
    except ValueError as exc:
        raise ValueError(f"{label}_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"{label}_PORT must be between 1 and 65535")
    return port


def _select_ports(api_override: int | None, ui_override: int | None) -> tuple[int, int]:
    if api_override is not None and not is_port_free(api_override):
        raise RuntimeError(f"API port {api_override} is already in use.")
    if ui_override is not None and not is_port_free(ui_override):
        raise RuntimeError(f"UI port {ui_override} is already in use.")

    if api_override is None and ui_override is None:
        return pick_two_free_ports()
    if api_override is None:
        return pick_free_port({ui_override}), ui_override
    if ui_override is None:
        return api_override, pick_free_port({api_override})
    if api_override == ui_override:
        raise RuntimeError("API and UI ports must be distinct.")
    return api_override, ui_override


def main() -> int:
    parser = argparse.ArgumentParser(description="Start Buff API + UI dev servers.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Start servers, wait until ready, then stay alive until interrupted.",
    )
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Disable API reload mode.",
    )
    parser.add_argument("--api-port", type=int, help="Explicit API port override.")
    parser.add_argument("--ui-port", type=int, help="Explicit UI port override.")
    parser.add_argument(
        "--max-seconds",
        type=float,
        help="Exit after this many seconds in --once mode.",
    )
    args = parser.parse_args()

    repo_root = _repo_root()

    try:
        runs_root = _resolve_runs_root(repo_root)
        _ensure_uvicorn_available()
        npm = _ensure_node_available(repo_root)
    except RuntimeError as exc:
        _log(f"ERROR: {exc}")
        return 1

    api_port_raw = str(args.api_port) if args.api_port is not None else os.environ.get("API_PORT")
    ui_port_raw = str(args.ui_port) if args.ui_port is not None else os.environ.get("UI_PORT")

    try:
        api_override = _parse_port(api_port_raw, "API")
        ui_override = _parse_port(ui_port_raw, "UI")
    except ValueError as exc:
        _log(f"ERROR: {exc}")
        return 1

    try:
        api_port, ui_port = _select_ports(api_override, ui_override)
    except RuntimeError as exc:
        message = str(exc)
        if message.startswith("API port"):
            return _handle_port_error("API", api_port_raw, exc)
        if message.startswith("UI port"):
            return _handle_port_error("UI", ui_port_raw, exc)
        return _fail(f"ERROR: {message}")

    clear_next_dev_lock(repo_root)

    reload_api = not args.no_reload and not args.once

    api_env = _with_pythonpath(os.environ.copy(), repo_root)
    api_env["RUNS_ROOT"] = str(runs_root)
    api_env["DEMO_MODE"] = "0"
    api_env["API_PORT"] = str(api_port)
    api_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "apps.api.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(api_port),
    ]
    if reload_api:
        api_cmd.append("--reload")
    _log(f"Starting API on http://127.0.0.1:{api_port} (RUNS_ROOT={runs_root})")
    api_proc = start_process(api_cmd, repo_root, api_env, "start_process")

    ui_env = os.environ.copy()
    ui_env["NEXT_PUBLIC_API_BASE"] = f"http://127.0.0.1:{api_port}/api/v1"
    ui_env["UI_PORT"] = str(ui_port)
    ui_cmd = [npm, "run", "dev", "--", "--port", str(ui_port)]
    _log(f"Starting UI on http://127.0.0.1:{ui_port}")
    ui_proc = start_process(ui_cmd, repo_root / "apps" / "web", ui_env, "start_process")

    pid_path = pidfile_path(repo_root)
    write_pidfile(
        pid_path,
        {
            "api": {"pid": api_proc.pid, "port": api_port},
            "ui": {"pid": ui_proc.pid, "port": ui_port},
            "started_at": time.time(),
            "mode": "dev_start",
        },
    )

    try:
        wait_http_200(f"http://127.0.0.1:{api_port}/api/v1/health", 60, expect_text="ok")
        wait_http_200(f"http://127.0.0.1:{ui_port}{UI_READY_PATH}", 120)
        _log("Dev servers ready.")
        _log(f"Open http://localhost:{ui_port}/runs/new")
        _log("Press Ctrl+C to stop.")
        if args.once:
            if args.max_seconds:
                time.sleep(args.max_seconds)
            else:
                while True:
                    time.sleep(1)
        else:
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
                kill_process_tree(proc, label)
        wait_port_free(ui_port)
        wait_port_free(api_port)
        if pid_path.exists():
            pid_path.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
