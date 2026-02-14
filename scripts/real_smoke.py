from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

DEFAULT_API_PORT = 8000
DEFAULT_UI_PORT = 3000
WORKSPACE_MARKER = 'data-testid="chart-workspace"'


def _log(message: str) -> None:
    print(message, flush=True)


def _ensure_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env) if base_env is not None else os.environ.copy()
    exe_dir = str(Path(sys.executable).resolve().parent)
    path = env.get("PATH", "")
    env["PATH"] = f"{exe_dir}{os.pathsep}{path}" if path else exe_dir
    return env


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


def start_process(cmd: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen:
    _log(f"Command (start_process): {cmd}")
    return subprocess.Popen(cmd, cwd=str(cwd), env=_ensure_env(env), **_process_kwargs())


def stop_process(proc: subprocess.Popen | None, label: str) -> None:
    if proc is None:
        return
    _log(f"Stopping {label}...")
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
        except OSError:
            return False


def is_port_free(port: int) -> bool:
    if _port_in_use(socket.AF_INET, "127.0.0.1", port):
        return False
    if _port_in_use(socket.AF_INET6, "::1", port):
        return False
    return _can_bind(socket.AF_INET, "127.0.0.1", port) and _can_bind(socket.AF_INET6, "::1", port)


def find_free_port(start: int, end: int) -> int:
    for port in range(start, end + 1):
        if is_port_free(port):
            return port
    raise RuntimeError(f"No free port available in range {start}-{end}")


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


def request_json(url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=20) as response:
        payload = response.read().decode("utf-8")
        return response.status, json.loads(payload)


def request_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=20) as response:
        return response.read().decode("utf-8", errors="ignore")


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


def _build_multipart(payload: dict[str, object], file_path: Path) -> tuple[bytes, str]:
    boundary = f"----buff-smoke-{uuid.uuid4().hex}"
    body = bytearray()

    def add_line(line: str) -> None:
        body.extend(line.encode("utf-8"))
        body.extend(b"\r\n")

    add_line(f"--{boundary}")
    add_line('Content-Disposition: form-data; name="request"')
    add_line("Content-Type: application/json")
    add_line("")
    body.extend(json.dumps(payload).encode("utf-8"))
    body.extend(b"\r\n")

    add_line(f"--{boundary}")
    add_line(f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"')
    add_line("Content-Type: text/csv")
    add_line("")
    body.extend(file_path.read_bytes())
    body.extend(b"\r\n")

    add_line(f"--{boundary}--")
    content_type = f"multipart/form-data; boundary={boundary}"
    return bytes(body), content_type


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    runs_root = repo_root / ".runs_smoke_real"
    csv_path = repo_root / "tests" / "fixtures" / "phase6" / "sample.csv"

    if not csv_path.exists():
        _log(f"CSV fixture not found: {csv_path}")
        return 1

    if runs_root.exists():
        shutil.rmtree(runs_root, ignore_errors=True)
    runs_root.mkdir(parents=True, exist_ok=True)

    api_proc: subprocess.Popen | None = None
    ui_proc: subprocess.Popen | None = None

    try:
        api_port = find_free_port(DEFAULT_API_PORT, DEFAULT_API_PORT + 20)
        ui_port = find_free_port(DEFAULT_UI_PORT, DEFAULT_UI_PORT + 20)

        api_env = _with_pythonpath(os.environ.copy(), repo_root)
        api_env["RUNS_ROOT"] = str(runs_root)
        api_env["DEMO_MODE"] = "0"
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
        api_base = f"http://127.0.0.1:{api_port}/api/v1"
        wait_for_http(f"{api_base}/health", expect_text="ok", timeout=60)

        ui_env = os.environ.copy()
        ui_env["NEXT_PUBLIC_API_BASE"] = api_base
        ui_cmd = resolve_ui_command(repo_root, ui_port)
        ui_proc = start_process(ui_cmd, repo_root / "apps" / "web", ui_env)
        ui_base = f"http://127.0.0.1:{ui_port}"
        wait_for_http(f"{ui_base}/runs/new", expect_text="Create Run", timeout=120)

        status, active = request_json(f"{api_base}/plugins/active")
        if status != 200:
            raise RuntimeError(f"/plugins/active returned {status}")
        if not active.get("strategies"):
            raise RuntimeError("No strategies returned from /plugins/active in DEMO_MODE=0")

        payload = {
            "schema_version": "1.0.0",
            "data_source": {
                "type": "csv",
                "path": "upload.csv",
                "symbol": "BTCUSDT",
                "timeframe": "1m",
            },
            "strategy": {"id": "hold", "params": {}},
            "risk": {"level": 3},
            "costs": {"commission_bps": 0.0, "slippage_bps": 0.0},
        }
        body, content_type = _build_multipart(payload, csv_path)
        create_url = f"{api_base}/runs"
        status, created = request_json(
            create_url, data=body, headers={"Content-Type": content_type}
        )
        if status not in {200, 201}:
            raise RuntimeError(f"Run creation failed: {status}")
        run_id = created.get("run_id")
        if not run_id:
            raise RuntimeError("run_id missing in create response")

        html = request_text(f"{ui_base}/runs/{run_id}")
        if WORKSPACE_MARKER not in html:
            raise RuntimeError("Run page missing chart workspace marker")

        for endpoint in ("summary", "metrics", "trades"):
            status, _ = request_json(f"{api_base}/runs/{run_id}/{endpoint}")
            if status != 200:
                raise RuntimeError(f"/runs/{run_id}/{endpoint} returned {status}")

        _log("real_smoke OK")
        return 0
    except Exception as exc:
        _log(f"real_smoke FAILED: {exc}")
        return 1
    finally:
        stop_process(ui_proc, "UI")
        stop_process(api_proc, "API")
        if runs_root.exists():
            shutil.rmtree(runs_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
