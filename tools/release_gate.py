from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

MAX_OUTPUT = 20_000

NETWORK_ERROR_HINTS = [
    "urlerror",
    "httperror",
    "temporary failure",
    "name or service not known",
    "network is unreachable",
    "connection reset",
    "connection refused",
    "timed out",
    "timeout",
    "tls",
    "ssl",
    "failed to fetch klines",
]


@dataclass
class StepFailure(Exception):
    step_name: str
    message: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _truncate(text: str | None, limit: int = MAX_OUTPUT) -> tuple[str, bool]:
    if text is None:
        return "", False
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _log(message: str) -> None:
    print(message, flush=True)


def _run_command(
    steps: list[dict[str, object]],
    name: str,
    cmd: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    allow_failure: bool = False,
) -> subprocess.CompletedProcess[str]:
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        duration = round(time.perf_counter() - start, 4)
        stdout_text = _coerce_text(exc.stdout)
        stderr_text = _coerce_text(exc.stderr)
        stdout, stdout_truncated = _truncate(stdout_text)
        stderr, stderr_truncated = _truncate(stderr_text)
        details = {
            "command": cmd,
            "command_str": " ".join(cmd),
            "timeout_seconds": timeout_seconds,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }
        steps.append(
            {
                "name": name,
                "status": "timeout",
                "duration": duration,
                "details": details,
            }
        )
        raise StepFailure(name, f"command timed out after {timeout_seconds}s")
    except Exception as exc:
        duration = round(time.perf_counter() - start, 4)
        details = {
            "command": cmd,
            "command_str": " ".join(cmd),
            "exception": repr(exc),
        }
        steps.append(
            {
                "name": name,
                "status": "fail",
                "duration": duration,
                "details": details,
            }
        )
        raise StepFailure(name, f"command failed to run: {exc}")

    stdout, stdout_truncated = _truncate(proc.stdout)
    stderr, stderr_truncated = _truncate(proc.stderr)
    duration = round(time.perf_counter() - start, 4)
    status = "ok" if proc.returncode == 0 else "fail"

    details = {
        "command": cmd,
        "command_str": " ".join(cmd),
        "return_code": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
    }

    steps.append(
        {
            "name": name,
            "status": status,
            "duration": duration,
            "details": details,
        }
    )

    if proc.returncode != 0 and not allow_failure:
        raise StepFailure(name, f"command failed with code {proc.returncode}")

    return proc


def _looks_like_network_failure(output: str) -> bool:
    lowered = output.lower()
    return any(hint in lowered for hint in NETWORK_ERROR_HINTS)


def _coerce_text(value: object | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _mvp_smoke_command() -> list[str]:
    return [
        sys.executable,
        "-m",
        "src.tools.mvp_smoke",
        "--symbols",
        "BTCUSDT",
        "ETHUSDT",
        "--timeframe",
        "1h",
        "--since",
        "2023-01-01",
        "--until",
        "2023-02-01",
        "--runs",
        "2",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local release gate.")
    parser.add_argument("--strict", action="store_true", help="Fail fast on first error.")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=900,
        help="Per-step timeout for subprocess commands.",
    )
    parser.add_argument(
        "--with-network-smoke",
        action="store_true",
        help="Run the MVP smoke test (requires network access).",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    report_path = repo_root / "reports" / "release_gate_report.json"

    steps: list[dict[str, object]] = []
    started_at = _utc_now_iso()
    overall_status = "fail"
    any_failed = False

    metadata: dict[str, object] = {
        "git_branch": None,
        "git_sha": None,
        "python_version": sys.version,
        "ruff_version": None,
        "pytest_version": None,
    }

    def run_step(name: str, cmd: list[str]) -> subprocess.CompletedProcess[str] | None:
        nonlocal any_failed
        try:
            proc = _run_command(
                steps,
                name,
                cmd,
                cwd=repo_root,
                timeout_seconds=args.timeout_seconds,
                allow_failure=True,
            )
        except StepFailure:
            any_failed = True
            if args.strict:
                raise
            return None
        if proc.returncode != 0:
            any_failed = True
            if args.strict:
                raise StepFailure(name, f"command failed with code {proc.returncode}")
        return proc

    try:
        _log("release_gate: git metadata")
        proc = run_step("git_branch", ["git", "rev-parse", "--abbrev-ref", "HEAD"])
        if proc is not None and proc.returncode == 0:
            value = (proc.stdout or "").strip()
            if value:
                metadata["git_branch"] = value

        proc = run_step("git_sha", ["git", "rev-parse", "HEAD"])
        if proc is not None and proc.returncode == 0:
            value = (proc.stdout or "").strip()
            if value:
                metadata["git_sha"] = value

        proc = run_step("ruff_version", [sys.executable, "-m", "ruff", "--version"])
        if proc is not None and proc.returncode == 0:
            value = (proc.stdout or "").strip()
            if value:
                metadata["ruff_version"] = value

        proc = run_step("pytest_version", [sys.executable, "-m", "pytest", "--version"])
        if proc is not None and proc.returncode == 0:
            value = (proc.stdout or "").strip()
            if value:
                metadata["pytest_version"] = value

        _log("release_gate: ruff check")
        run_step("ruff_check", [sys.executable, "-m", "ruff", "check", "."])

        _log("release_gate: ruff format --check")
        run_step("ruff_format_check", [sys.executable, "-m", "ruff", "format", "--check", "."])

        _log("release_gate: pytest -q")
        run_step("pytest", [sys.executable, "-m", "pytest", "-q"])

        _log("release_gate: s1_online_data_plane")
        run_step(
            "s1_online_data_plane",
            [sys.executable, "-m", "pytest", "-q", "tools/test_s1_online_data_plane.py"],
        )

        _log("release_gate: s2_double_run_compare")
        run_step(
            "s2_double_run_compare",
            [sys.executable, "-m", "pytest", "-q", "tools/test_s2_double_run_compare.py"],
        )

        _log("release_gate: s2_no_network")
        run_step(
            "s2_no_network",
            [sys.executable, "-m", "pytest", "-q", "tools/test_s2_no_network.py"],
        )

        _log("release_gate: s2_artifact_pack_completeness")
        run_step(
            "s2_artifact_pack_completeness",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tools/test_s2_artifact_pack_completeness.py",
            ],
        )

        _log("release_gate: s3_double_run_compare")
        run_step(
            "s3_double_run_compare",
            [sys.executable, "-m", "pytest", "-q", "tools/test_s3_double_run_compare.py"],
        )

        _log("release_gate: s3_input_digest_verification")
        run_step(
            "s3_input_digest_verification",
            [sys.executable, "-m", "pytest", "-q", "tools/test_s3_input_digest_verification.py"],
        )

        _log("release_gate: s3_cross_tenant_isolation")
        run_step(
            "s3_cross_tenant_isolation",
            [sys.executable, "-m", "pytest", "-q", "tools/test_s3_cross_tenant_isolation.py"],
        )

        _log("release_gate: s3_no_network")
        run_step(
            "s3_no_network",
            [sys.executable, "-m", "pytest", "-q", "tools/test_s3_no_network.py"],
        )

        _log("release_gate: s3_no_live_execution_path")
        run_step(
            "s3_no_live_execution_path",
            [sys.executable, "-m", "pytest", "-q", "tools/test_s3_no_live_execution_path.py"],
        )

        _log("release_gate: s3_artifact_pack_completeness")
        run_step(
            "s3_artifact_pack_completeness",
            [sys.executable, "-m", "pytest", "-q", "tools/test_s3_artifact_pack_completeness.py"],
        )

        _log("release_gate: s3_smoke_demo")
        run_step(
            "s3_smoke_demo",
            [sys.executable, "-m", "pytest", "-q", "tools/test_s3_smoke_demo.py"],
        )

        _log("release_gate: s4_risk_fail_closed")
        run_step(
            "s4_risk_fail_closed",
            [sys.executable, "-m", "pytest", "-q", "tools/test_s4_risk_fail_closed.py"],
        )

        _log("release_gate: s4_risk_contract_surface")
        run_step(
            "s4_risk_contract_surface",
            [sys.executable, "-m", "pytest", "-q", "tools/test_s4_risk_contract_surface.py"],
        )

        _log("release_gate: s4_risk_artifact_presence")
        run_step(
            "s4_risk_artifact_presence",
            [sys.executable, "-m", "pytest", "-q", "tools/test_s4_risk_artifact_presence.py"],
        )

        _log("release_gate: s6_observability_surface")
        run_step(
            "s6_observability_surface",
            [sys.executable, "-m", "pytest", "-q", "tools/test_s6_observability_surface.py"],
        )

        _log("release_gate: s6_sim_only_invariant")
        run_step(
            "s6_sim_only_invariant",
            [sys.executable, "-m", "pytest", "-q", "tools/test_s6_sim_only_invariant.py"],
        )

        _log("release_gate: s6_no_network_runtime_surface")
        run_step(
            "s6_no_network_runtime_surface",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tools/test_s6_no_network_runtime_surface.py",
            ],
        )

        _log("release_gate: s7_experiment_artifact_contract")
        run_step(
            "s7_experiment_artifact_contract",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tools/test_s7_experiment_artifact_contract.py",
            ],
        )

        _log("release_gate: s7_experiment_determinism")
        run_step(
            "s7_experiment_determinism",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tools/test_s7_experiment_determinism.py",
            ],
        )

        _log("release_gate: s7_experiment_fail_closed_partial")
        run_step(
            "s7_experiment_fail_closed_partial",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tools/test_s7_experiment_fail_closed_partial.py",
            ],
        )

        _log("release_gate: s7_experiment_caps_enforced")
        run_step(
            "s7_experiment_caps_enforced",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tools/test_s7_experiment_caps_enforced.py",
            ],
        )

        _log("release_gate: s7_experiment_lock_enforced")
        run_step(
            "s7_experiment_lock_enforced",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tools/test_s7_experiment_lock_enforced.py",
            ],
        )

        if args.with_network_smoke:
            _log("release_gate: mvp_smoke (network)")
            proc = run_step("mvp_smoke", _mvp_smoke_command())
            if proc is not None and proc.returncode != 0:
                combined = f"{proc.stdout}\n{proc.stderr}"
                if _looks_like_network_failure(combined):
                    message = (
                        "mvp_smoke downloads Binance 1m data over the network and no offline "
                        "mode is available. Keep --with-network-smoke disabled in offline "
                        "environments, or add an offline mode before running this step."
                    )
                    steps[-1]["details"]["actionable_message"] = message
                    print(f"error: {message}", file=sys.stderr)
        else:
            steps.append(
                {
                    "name": "mvp_smoke",
                    "status": "skipped",
                    "duration": 0.0,
                    "details": {
                        "reason": "with_network_smoke_not_enabled",
                        "message": "Skipped deterministic smoke by default (no network).",
                    },
                }
            )

        overall_status = "pass" if not any_failed else "fail"
        _log(f"release_gate: {overall_status.upper()}")
        return_code = 0 if not any_failed else 1
    except StepFailure as exc:
        any_failed = True
        _log(f"release_gate: FAIL ({exc.step_name})")
        return_code = 1
    finally:
        report = {
            "timestamp_utc": started_at,
            "finished_at_utc": _utc_now_iso(),
            "strict": bool(args.strict),
            "with_network_smoke": bool(args.with_network_smoke),
            "git_branch": metadata["git_branch"],
            "git_sha": metadata["git_sha"],
            "python_version": metadata["python_version"],
            "ruff_version": metadata["ruff_version"],
            "pytest_version": metadata["pytest_version"],
            "steps": steps,
            "overall_status": overall_status,
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        _log(f"release_gate: report -> {report_path}")

    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
