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


STEPS = [
    ("ruff check", [sys.executable, "-m", "ruff", "check", "."]),
    ("ruff format", [sys.executable, "-m", "ruff", "format", "--check", "."]),
    ("pytest", [sys.executable, "-m", "pytest", "-q"]),
    ("ui smoke", ["node", "apps/web/scripts/ui-smoke.mjs"]),
]

DEFAULT_API_PORT = 8000
DEFAULT_UI_PORT = 3000
PORT_RELEASE_TIMEOUT = 10
PORT_RELEASE_TIMEOUT = 10
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


def start_process(cmd: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen:
    _log_command("start_process", cmd)
    return subprocess.Popen(cmd, cwd=str(cwd), env=_ensure_env(env), **_process_kwargs())


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


def wait_for_port_release(port: int, *, timeout: float = PORT_RELEASE_TIMEOUT) -> bool:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if is_port_free(port):
            return True
        time.sleep(0.2)
    return False


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


def _pick_ephemeral_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _resolve_preferred_port(raw: str | None, default: int, label: str) -> int:
    if raw is None or raw == "":
        return default
    try:
        port = int(raw)
    except ValueError as exc:
        raise ValueError(f"{label}_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"{label}_PORT must be between 1 and 65535")
    return port


def _select_port(preferred: int, label: str) -> int:
    if is_port_free(preferred):
        return preferred
    for _ in range(50):
        candidate = _pick_ephemeral_port()
        if candidate != preferred and is_port_free(candidate):
            return candidate
    raise RuntimeError(f"No free {label} port found")


def _pick_ephemeral_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _resolve_preferred_port(raw: str | None, default: int, label: str) -> int:
    if raw is None or raw == "":
        return default
    try:
        port = int(raw)
    except ValueError as exc:
        raise ValueError(f"{label}_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"{label}_PORT must be between 1 and 65535")
    return port


def _select_port(preferred: int, label: str) -> int:
    if is_port_free(preferred):
        return preferred
    for _ in range(50):
        candidate = _pick_ephemeral_port()
        if candidate != preferred and is_port_free(candidate):
            return candidate
    raise RuntimeError(f"No free {label} port found")


def detect_running_ui(ports: list[int]) -> int | None:
    for port in ports:
        url = f"http://127.0.0.1:{port}/runs/phase1_demo"
        if probe_http(url, expect_text=UI_WORKSPACE_MARKER, timeout=1):
            return port
    return None


def detect_running_api(port: int) -> bool:
    url = f"http://127.0.0.1:{port}/api/v1/health"
    if not probe_http(url, expect_text="ok", timeout=1):
        return False
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/runs", timeout=2) as response:
            body = response.read().decode("utf-8", errors="ignore")
        return "phase1_demo" in body
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
        print("WARN: next dev appears to be running; skipping lock removal.")
        return
    try:
        lock_path.unlink()
        print("Removed stale Next.js dev lock.")
    except OSError as exc:
        print(f"WARN: failed to remove Next.js dev lock: {exc}")


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
        print("WARN: next dev appears to be running; skipping lock removal.")
        return
    try:
        lock_path.unlink()
        print("Removed stale Next.js dev lock.")
    except OSError as exc:
        print(f"WARN: failed to remove Next.js dev lock: {exc}")


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
    api_started = False
    ui_started = False
    raw_api_port = os.environ.get("API_PORT")
    raw_ui_port = os.environ.get("UI_PORT")
    try:
        api_port = _resolve_preferred_port(raw_api_port, DEFAULT_API_PORT, "API")
        ui_port = _resolve_preferred_port(raw_ui_port, DEFAULT_UI_PORT, "UI")
    except ValueError as exc:
        print(f"!! {exc}")
        return 1
    preferred_api_port = api_port
    preferred_ui_port = ui_port
    ui_override = raw_ui_port not in (None, "")

    try:
        if args.with_services:
            print("Starting Phase-1 services...")
            try:
                if detect_running_api(api_port):
                    print(f"API already running on {api_port}, reusing")
                else:
                    if not is_port_free(api_port):
                        api_port = _select_port(api_port, "API")
                        print(f"API port {preferred_api_port} busy, using {api_port}")

                    api_env = _with_pythonpath(os.environ.copy(), repo_root)
                    api_env["ARTIFACTS_ROOT"] = str(repo_root / "tests" / "fixtures" / "artifacts")
                    api_env["DEMO_MODE"] = "1"
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
                    )
                    api_started = True
                    api_url = f"http://127.0.0.1:{api_port}/api/v1/health"
                    wait_for_http(api_url, expect_text="ok", timeout=60)

                if ui_override:
                    running_ui = detect_running_ui([ui_port])
                else:
                    running_ui = detect_running_ui([DEFAULT_UI_PORT] + list(range(3001, 3011)))
                if running_ui is not None:
                    ui_port = running_ui
                    print(f"UI already running on {ui_port}, reusing")
                else:
                    if not is_port_free(ui_port):
                        ui_port = _select_port(ui_port, "UI")
                        print(f"UI port {preferred_ui_port} busy, using {ui_port}")

                    _clear_next_dev_lock(repo_root)
                    ui_env = os.environ.copy()
                    ui_env["NEXT_PUBLIC_API_BASE"] = f"http://127.0.0.1:{api_port}/api/v1"
                    ui_cmd = resolve_ui_command(repo_root, ui_port)
                    ui_proc = start_process(
                        ui_cmd,
                        repo_root / "apps" / "web",
                        ui_env,
                    )
                    ui_started = True
                    ui_url = f"http://127.0.0.1:{ui_port}/runs/phase1_demo"
                    wait_for_http(ui_url, expect_text=UI_WORKSPACE_MARKER, timeout=120)

                print(f"verify_phase1: using API_PORT={api_port}, UI_PORT={ui_port}")
            except Exception as exc:
                print(f"!! service startup failed: {exc}")
                return 1

        env = os.environ.copy()
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
                stop_process(ui_proc, "UI")
                stop_process(api_proc, "API")
                if ui_started:
                    wait_for_port_release(ui_port)
                if api_started:
                    wait_for_port_release(api_port)
                ui_proc = None
                api_proc = None
                ui_started = False
                api_started = False
            code = run_step(label, cmd, repo_root, env=env)
            if code != 0:
                return code

        print("\nPhase-1 verification complete")
        return 0
    finally:
        if args.with_services and not args.no_teardown:
            stop_process(ui_proc, "UI")
            stop_process(api_proc, "API")
            if ui_started:
                wait_for_port_release(ui_port)
            if api_started:
                wait_for_port_release(api_port)


if __name__ == "__main__":
    sys.exit(main())
