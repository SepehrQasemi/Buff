from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _orchestrator import (  # noqa: E402
    is_port_free,
    kill_process_tree,
    pick_free_port,
    pick_two_free_ports,
    start_process,
    wait_http_200,
)

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


def _port_from_url(raw: str) -> int | None:
    try:
        parsed = urlparse(raw)
    except Exception:
        return None
    if parsed.port:
        return parsed.port
    return None


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
        api_base_env = os.environ.get("API_BASE_URL") or os.environ.get("API_BASE")
        ui_base_env = os.environ.get("UI_BASE_URL") or os.environ.get("UI_BASE")
        api_override = _parse_port(os.environ.get("API_PORT"), "API")
        ui_override = _parse_port(os.environ.get("UI_PORT"), "UI")

        if api_base_env:
            parsed = _port_from_url(api_base_env)
            if parsed:
                api_override = parsed
        if ui_base_env:
            parsed = _port_from_url(ui_base_env)
            if parsed:
                ui_override = parsed

        api_port, ui_port = _select_ports(api_override, ui_override)

        api_env = _with_pythonpath(os.environ.copy(), repo_root)
        api_env["RUNS_ROOT"] = str(runs_root)
        api_env["DEMO_MODE"] = "0"
        api_env = _ensure_env(api_env)
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
        api_base = f"http://127.0.0.1:{api_port}/api/v1"
        if api_base_env and api_port == api_override:
            api_base = api_base_env.rstrip("/")
        wait_http_200(f"{api_base}/health", 60, expect_text="ok")

        ui_env = _ensure_env(os.environ.copy())
        ui_env["NEXT_PUBLIC_API_BASE"] = api_base
        ui_cmd = resolve_ui_command(repo_root, ui_port)
        ui_proc = start_process(ui_cmd, repo_root / "apps" / "web", ui_env, "start_process")
        ui_base = f"http://127.0.0.1:{ui_port}"
        if ui_base_env and ui_port == ui_override:
            ui_base = ui_base_env.rstrip("/")
        wait_http_200(f"{ui_base}/runs/new", 120, expect_text="Create Run")

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
        kill_process_tree(ui_proc, "UI")
        kill_process_tree(api_proc, "API")
        if runs_root.exists():
            shutil.rmtree(runs_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
