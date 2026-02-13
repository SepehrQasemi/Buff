from __future__ import annotations

import argparse
import errno
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
DEFAULT_DEMO_RUN_ID = "stage5_demo"
UI_WORKSPACE_MARKER = 'data-testid="chart-workspace"'


def _in_venv() -> bool:
    return getattr(sys, "base_prefix", sys.prefix) != sys.prefix


def _resolve_python_executable(repo_root: Path) -> str:
    candidates = [
        repo_root / ".venv" / "Scripts" / "python.exe",
        repo_root / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _ensure_env(
    base_env: dict[str, str] | None = None,
    *,
    python_exe: str | None = None,
    repo_root: Path | None = None,
) -> dict[str, str]:
    env = dict(base_env) if base_env is not None else os.environ.copy()
    exe_dir = str(Path(python_exe or sys.executable).resolve().parent)
    path = env.get("PATH", "")
    env["PATH"] = f"{exe_dir}{os.pathsep}{path}" if path else exe_dir
    if python_exe:
        exe_path = Path(python_exe).resolve()
        if exe_path.parent.name in {"Scripts", "bin"}:
            env["VIRTUAL_ENV"] = str(exe_path.parent.parent)
    elif _in_venv():
        env["VIRTUAL_ENV"] = sys.prefix
    if repo_root is not None:
        src_path = repo_root / "src"
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(src_path) + (os.pathsep + existing if existing else "")
    return env


def _log_command(label: str, cmd: list[str]) -> None:
    print(f"Command ({label}): {cmd}")


def run_step(
    label: str,
    cmd: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    *,
    python_exe: str | None = None,
    repo_root: Path | None = None,
) -> int:
    print(f"\n==> {label}")
    _log_command(label, cmd)
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=_ensure_env(env, python_exe=python_exe, repo_root=repo_root),
    )
    if result.returncode != 0:
        print(f"!! {label} failed (exit {result.returncode})")
    else:
        print(f"OK {label}")
    return result.returncode


def _print_summary(results: list[tuple[str, int]]) -> None:
    print("\nSummary:")
    if not results:
        print("- No steps executed.")
        return
    for label, code in results:
        status = "OK" if code == 0 else f"FAIL (exit {code})"
        print(f"- {label}: {status}")


def probe_http(url: str, *, expect_text: str | None, timeout: float) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="ignore")
            if expect_text and expect_text not in body:
                return False
            return True
    except Exception:
        return False


def wait_for_http(url: str, *, expect_text: str | None, timeout: float) -> None:
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


def _process_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def start_process(
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
    *,
    python_exe: str | None = None,
    repo_root: Path | None = None,
) -> subprocess.Popen:
    _log_command("start_process", cmd)
    return subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=_ensure_env(env, python_exe=python_exe, repo_root=repo_root),
        **_process_kwargs(),
    )


def stop_process(proc: subprocess.Popen | None, label: str) -> None:
    if proc is None:
        return
    print(f"\nStopping {label}...")
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return
        except Exception:
            pass
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


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
        except OSError as exc:
            if getattr(exc, "errno", None) == errno.EADDRNOTAVAIL:
                return True
            return False


def is_port_free(port: int) -> bool:
    if _port_in_use(socket.AF_INET, "127.0.0.1", port):
        return False
    if _port_in_use(socket.AF_INET6, "::1", port):
        return False
    ipv4_free = _can_bind(socket.AF_INET, "127.0.0.1", port)
    ipv6_free = _can_bind(socket.AF_INET6, "::1", port)
    return ipv4_free and ipv6_free


def find_free_port(start: int, end: int) -> int:
    for port in range(start, end + 1):
        if is_port_free(port):
            return port
    raise RuntimeError(f"No free port available in range {start}-{end}")


def detect_running_ui(run_id: str, ports: list[int]) -> int | None:
    for port in ports:
        url = f"http://127.0.0.1:{port}/runs/{run_id}"
        if probe_http(url, expect_text=UI_WORKSPACE_MARKER, timeout=1):
            return port
    return None


def detect_running_api(port: int) -> bool:
    url = f"http://127.0.0.1:{port}/api/v1/health"
    return probe_http(url, expect_text="ok", timeout=1)


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase-6 Stage-5 verification gate.")
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
        "--demo-run-id",
        default=DEFAULT_DEMO_RUN_ID,
        help="Run id to validate for the demo render check.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    python_exe = _resolve_python_executable(repo_root)
    print(f"Python executable: {python_exe}")
    api_proc: subprocess.Popen | None = None
    ui_proc: subprocess.Popen | None = None
    api_port = DEFAULT_API_PORT
    ui_port = DEFAULT_UI_PORT
    demo_run_id = args.demo_run_id
    results: list[tuple[str, int]] = []
    steps = [
        ("ruff format", [python_exe, "-m", "ruff", "format", "--check", "."]),
        ("ruff check", [python_exe, "-m", "ruff", "check", "."]),
        ("pytest", [python_exe, "-m", "pytest", "-q"]),
        ("web smoke", ["node", "apps/web/scripts/smoke.mjs"]),
        ("ui smoke", ["node", "apps/web/scripts/ui-smoke.mjs"]),
        ("demo render check", ["node", "apps/web/scripts/demo-render-check.mjs"]),
    ]

    try:
        if args.with_services:
            print("Starting Stage-5 demo services...")
            try:
                if detect_running_api(api_port):
                    print(f"API already running on {api_port}, reusing")
                else:
                    if not is_port_free(api_port):
                        try:
                            api_port = find_free_port(8001, 8010)
                        except RuntimeError as exc:
                            raise RuntimeError(
                                "API port busy and no free port available in 8000-8010. "
                                "Stop the service using those ports or run without --with-services."
                            ) from exc
                        print(f"API port {DEFAULT_API_PORT} busy, using {api_port}")

                    api_env = os.environ.copy()
                    api_env["ARTIFACTS_ROOT"] = str(repo_root / "tests" / "fixtures" / "artifacts")
                    api_env.pop("RUNS_ROOT", None)
                    api_proc = start_process(
                        [
                            python_exe,
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
                        python_exe=python_exe,
                        repo_root=repo_root,
                    )
                    api_url = f"http://127.0.0.1:{api_port}/api/v1/health"
                    wait_for_http(api_url, expect_text="ok", timeout=60)

                running_ui = detect_running_ui(
                    demo_run_id, [DEFAULT_UI_PORT] + list(range(3001, 3011))
                )
                if running_ui is not None:
                    ui_port = running_ui
                    print(f"UI already running on {ui_port}, reusing")
                else:
                    if not is_port_free(ui_port):
                        try:
                            ui_port = find_free_port(3001, 3010)
                        except RuntimeError as exc:
                            raise RuntimeError(
                                "UI port busy and no free port available in 3000-3010. "
                                "Stop the service using those ports or run without --with-services."
                            ) from exc
                        print(f"UI port {DEFAULT_UI_PORT} busy, using {ui_port}")

                    ui_env = os.environ.copy()
                    ui_env["NEXT_PUBLIC_API_BASE"] = f"http://127.0.0.1:{api_port}/api/v1"
                    ui_cmd = resolve_ui_command(repo_root, ui_port)
                    ui_proc = start_process(
                        ui_cmd,
                        repo_root / "apps" / "web",
                        ui_env,
                        python_exe=python_exe,
                        repo_root=repo_root,
                    )
                    ui_url = f"http://127.0.0.1:{ui_port}/runs/{demo_run_id}"
                    wait_for_http(ui_url, expect_text=UI_WORKSPACE_MARKER, timeout=120)
            except Exception as exc:
                print(f"!! service startup failed: {exc}")
                _print_summary(results)
                return 1

        env = os.environ.copy()
        env["API_BASE"] = f"http://127.0.0.1:{api_port}/api/v1"
        env["UI_BASE"] = f"http://127.0.0.1:{ui_port}"
        env["DEMO_RUN_ID"] = demo_run_id
        for label, cmd in steps:
            code = run_step(
                label,
                cmd,
                repo_root,
                env=env,
                python_exe=python_exe,
                repo_root=repo_root,
            )
            results.append((label, code))
            if code != 0:
                _print_summary(results)
                return code

        _print_summary(results)
        print("\nPhase-6 Stage-5 verification complete")
        return 0
    finally:
        if args.with_services and not args.no_teardown:
            stop_process(ui_proc, "UI")
            stop_process(api_proc, "API")


if __name__ == "__main__":
    sys.exit(main())
