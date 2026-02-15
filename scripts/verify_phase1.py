from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _orchestrator import (  # noqa: E402
    clear_next_dev_lock,
    is_port_free,
    kill_pid_tree,
    kill_process_tree,
    pidfile_path,
    pick_free_port,
    pick_two_free_ports,
    read_pidfile,
    start_process,
    wait_http_200,
    wait_port_free,
    write_pidfile,
)

STEPS = [
    ("ruff check", [sys.executable, "-m", "ruff", "check", "."]),
    ("ruff format", [sys.executable, "-m", "ruff", "format", "--check", "."]),
    ("pytest", [sys.executable, "-m", "pytest", "-q"]),
    ("ui smoke", ["node", "apps/web/scripts/ui-smoke.mjs"]),
]

UI_WORKSPACE_MARKER = 'data-testid="chart-workspace"'


def _in_venv() -> bool:
    return getattr(sys, "base_prefix", sys.prefix) != sys.prefix


def _ensure_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env) if base_env is not None else os.environ.copy()
    exe_dir = str(Path(sys.executable).resolve().parent)
    path = env.get("PATH", "")
    env["PATH"] = f"{exe_dir}{os.pathsep}{path}" if path else exe_dir
    if _in_venv():
        env["VIRTUAL_ENV"] = sys.prefix
    return env


def _with_pythonpath(env: dict[str, str], repo_root: Path) -> dict[str, str]:
    updated = dict(env)
    src_path = repo_root / "src"
    existing = updated.get("PYTHONPATH")
    updated["PYTHONPATH"] = str(src_path) + (os.pathsep + existing if existing else "")
    return updated


def _log_command(label: str, cmd: list[str]) -> None:
    print(f"Command ({label}): {cmd}")


def run_step(label: str, cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> int:
    print(f"\n==> {label}")
    _log_command(label, cmd)
    result = subprocess.run(cmd, cwd=str(cwd), env=_ensure_env(env))
    if result.returncode != 0:
        print(f"!! {label} failed (exit {result.returncode})")
    else:
        print(f"OK {label}")
    return result.returncode


def probe_http(url: str, *, expect_text: str | None, timeout: float) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="ignore")
            if expect_text and expect_text not in body:
                return False
            return True
    except Exception:
        return False


def resolve_ui_command(repo_root: Path, port: int) -> list[str]:
    npm = shutil.which("npm")
    if npm:
        return [npm, "run", "dev", "--", "--port", str(port)]

    bin_name = "next.cmd" if os.name == "nt" else "next"
    next_bin = repo_root / "apps" / "web" / "node_modules" / ".bin" / bin_name
    if next_bin.exists():
        return [str(next_bin), "dev", "--port", str(port)]

    node = shutil.which("node")
    next_js = repo_root / "apps" / "web" / "node_modules" / "next" / "dist" / "bin" / "next"
    if node and next_js.exists():
        return [node, str(next_js), "dev", "--port", str(port)]

    raise RuntimeError("npm or node not found for UI startup")


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
    parser = argparse.ArgumentParser(description="Phase-1 verification gate.")
    parser.add_argument(
        "--with-services",
        action="store_true",
        help="Start API/UI locally before running checks.",
    )
    parser.add_argument(
        "--no-teardown",
        action="store_true",
        help="Leave services running after verification.",
    )
    parser.add_argument(
        "--real-smoke",
        action="store_true",
        help="Run real-user smoke with DEMO_MODE=0 and file upload.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    print(f"Python executable: {sys.executable}")

    api_proc: subprocess.Popen | None = None
    ui_proc: subprocess.Popen | None = None
    api_port: int | None = None
    ui_port: int | None = None
    pid_path = pidfile_path(repo_root)

    def cleanup_services() -> None:
        ui_closed = True
        api_closed = True
        if ui_proc is not None:
            kill_process_tree(ui_proc, "UI")
        if api_proc is not None:
            kill_process_tree(api_proc, "API")
        if ui_port is not None:
            ui_closed = wait_port_free(ui_port)
        if api_port is not None:
            api_closed = wait_port_free(api_port)
        if (not ui_closed or not api_closed) and pid_path.exists():
            data = read_pidfile(pid_path) or {}
            for label in ("ui", "api"):
                entry = data.get(label, {})
                pid = entry.get("pid")
                if pid:
                    try:
                        kill_pid_tree(int(pid), label.upper())
                    except (TypeError, ValueError):
                        continue
            if ui_port is not None:
                wait_port_free(ui_port)
            if api_port is not None:
                wait_port_free(api_port)
        if pid_path.exists():
            pid_path.unlink()

    try:
        if args.with_services:
            print("Starting Phase-1 services...")
            try:
                api_override = _parse_port(os.environ.get("API_PORT"), "API")
                ui_override = _parse_port(os.environ.get("UI_PORT"), "UI")
                api_port, ui_port = _select_ports(api_override, ui_override)

                api_env = _with_pythonpath(os.environ.copy(), repo_root)
                api_env["ARTIFACTS_ROOT"] = str(repo_root / "tests" / "fixtures" / "artifacts")
                api_env["DEMO_MODE"] = "1"
                api_env["API_PORT"] = str(api_port)
                api_proc = start_process(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "apps.api.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(api_port),
                    ],
                    repo_root,
                    api_env,
                    "start_process",
                )
                api_url = f"http://127.0.0.1:{api_port}/api/v1/health"
                wait_http_200(api_url, 60, expect_text="ok")

                clear_next_dev_lock(repo_root)
                ui_env = os.environ.copy()
                ui_env["NEXT_PUBLIC_API_BASE"] = f"http://127.0.0.1:{api_port}/api/v1"
                ui_env["UI_PORT"] = str(ui_port)
                ui_cmd = resolve_ui_command(repo_root, ui_port)
                ui_proc = start_process(
                    ui_cmd,
                    repo_root / "apps" / "web",
                    ui_env,
                    "start_process",
                )
                ui_url = f"http://127.0.0.1:{ui_port}/runs/phase1_demo"
                wait_http_200(ui_url, 120, expect_text=UI_WORKSPACE_MARKER)

                write_pidfile(
                    pid_path,
                    {
                        "api": {"pid": api_proc.pid, "port": api_port},
                        "ui": {"pid": ui_proc.pid, "port": ui_port},
                        "started_at": time.time(),
                        "mode": "verify",
                    },
                )

                print(f"verify_phase1: using API_PORT={api_port}, UI_PORT={ui_port}")
            except Exception as exc:
                print(f"!! service startup failed: {exc}")
                cleanup_services()
                return 1

        env = os.environ.copy()
        if api_port is not None and ui_port is not None:
            api_base = f"http://127.0.0.1:{api_port}/api/v1"
            ui_base = f"http://127.0.0.1:{ui_port}"
            env["API_BASE"] = api_base
            env["API_BASE_URL"] = api_base
            env["API_PORT"] = str(api_port)
            env["UI_BASE"] = ui_base
            env["UI_BASE_URL"] = ui_base
            env["UI_PORT"] = str(ui_port)

        steps = list(STEPS)
        if args.real_smoke:
            steps.append(("real smoke", [sys.executable, "scripts/real_smoke.py"]))

        for label, cmd in steps:
            if label == "real smoke" and args.with_services:
                cleanup_services()
            code = run_step(label, cmd, repo_root, env=env)
            if code != 0:
                return code

        print("\nPhase-1 verification complete")
        return 0
    finally:
        if args.with_services and not args.no_teardown:
            cleanup_services()


if __name__ == "__main__":
    sys.exit(main())
