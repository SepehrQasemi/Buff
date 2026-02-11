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


def _run_and_check(
    steps: list[dict[str, object]],
    name: str,
    cmd: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    check_fn,
) -> subprocess.CompletedProcess[str]:
    proc = _run_command(
        steps,
        name,
        cmd,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        allow_failure=True,
    )
    if proc.returncode != 0:
        raise StepFailure(name, f"command failed with code {proc.returncode}")

    ok, extra_details, failure_message = check_fn(proc)
    steps[-1]["details"].update(extra_details)
    if not ok:
        steps[-1]["status"] = "fail"
        raise StepFailure(name, failure_message)

    return proc


def _check_inside_work_tree(
    proc: subprocess.CompletedProcess[str],
) -> tuple[bool, dict[str, object], str]:
    value = (proc.stdout or "").strip().lower()
    ok = value == "true"
    details = {"is_inside_work_tree": ok, "raw_value": value}
    return ok, details, "not inside a git work tree"


def _check_clean_status(
    proc: subprocess.CompletedProcess[str],
) -> tuple[bool, dict[str, object], str]:
    output = proc.stdout or ""
    is_clean = output.strip() == ""
    details = {"is_clean": is_clean, "porcelain": output}
    return is_clean, details, "working tree is dirty"


def _check_non_empty(label: str):
    def _inner(proc: subprocess.CompletedProcess[str]) -> tuple[bool, dict[str, object], str]:
        value = (proc.stdout or "").strip()
        ok = bool(value)
        details = {label: value}
        return ok, details, f"unable to read {label}"

    return _inner


def _coerce_text(value: object | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _check_branch_exists(
    steps: list[dict[str, object]],
    *,
    cwd: Path,
    timeout_seconds: int,
) -> None:
    start = time.perf_counter()
    local = _run_command(
        steps,
        "git_show_ref_main_local",
        ["git", "show-ref", "--verify", "refs/heads/main"],
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        allow_failure=True,
    )
    local_exists = local.returncode == 0
    steps[-1]["details"]["exists"] = local_exists
    if not local_exists:
        steps[-1]["status"] = "not_found"

    origin = None
    origin_exists = False
    if not local_exists:
        origin = _run_command(
            steps,
            "git_show_ref_main_origin",
            ["git", "show-ref", "--verify", "refs/remotes/origin/main"],
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            allow_failure=True,
        )
        origin_exists = origin.returncode == 0
        steps[-1]["details"]["exists"] = origin_exists
        if not origin_exists:
            steps[-1]["status"] = "not_found"

    duration = round(time.perf_counter() - start, 4)
    summary = {
        "name": "git_verify_main_branch",
        "status": "ok" if (local_exists or origin_exists) else "fail",
        "duration": duration,
        "details": {
            "local_exists": local_exists,
            "origin_exists": origin_exists,
        },
    }
    steps.append(summary)

    if not (local_exists or origin_exists):
        raise StepFailure("git_verify_main_branch", "main branch not found locally or on origin")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run release preflight (local, ff-only).")
    parser.add_argument(
        "--strict",
        dest="strict",
        action="store_true",
        default=True,
        help="Run release gate in strict mode (default).",
    )
    parser.add_argument(
        "--no-strict",
        dest="strict",
        action="store_false",
        help="Run release gate in non-strict mode.",
    )
    parser.add_argument(
        "--with-network-smoke",
        action="store_true",
        help="Forward --with-network-smoke to release gate.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=900,
        help="Per-step timeout for subprocess commands.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    report_path = repo_root / "reports" / "release_preflight_report.json"

    steps: list[dict[str, object]] = []
    started_at = _utc_now_iso()
    overall_status = "fail"
    starting_branch: str | None = None
    starting_sha: str | None = None
    ending_branch: str | None = None
    ending_sha: str | None = None
    dirty_tree_reported = False
    custom_error_reported = False

    try:
        _log("release_preflight: verify git repo")
        _run_and_check(
            steps,
            "git_rev_parse_is_inside_work_tree",
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=repo_root,
            timeout_seconds=args.timeout_seconds,
            check_fn=_check_inside_work_tree,
        )

        _log("release_preflight: capture starting branch")
        branch_proc = _run_and_check(
            steps,
            "git_starting_branch",
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root,
            timeout_seconds=args.timeout_seconds,
            check_fn=_check_non_empty("branch"),
        )
        starting_branch = (branch_proc.stdout or "").strip()

        _log("release_preflight: capture starting sha")
        sha_proc = _run_and_check(
            steps,
            "git_starting_sha",
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            timeout_seconds=args.timeout_seconds,
            check_fn=_check_non_empty("sha"),
        )
        starting_sha = (sha_proc.stdout or "").strip()

        _log("release_preflight: ensure clean working tree")
        try:
            _run_and_check(
                steps,
                "git_status_clean_before",
                ["git", "status", "--porcelain"],
                cwd=repo_root,
                timeout_seconds=args.timeout_seconds,
                check_fn=_check_clean_status,
            )
        except StepFailure as exc:
            if exc.step_name == "git_status_clean_before":
                details = steps[-1].get("details", {}) if steps else {}
                porcelain = details.get("porcelain", "")
                if isinstance(porcelain, str) and porcelain.strip():
                    print("error: working tree is dirty", file=sys.stderr)
                    dirty_tree_reported = True
                    for line in porcelain.splitlines()[:20]:
                        print(line, file=sys.stderr)
            raise

        _log("release_preflight: git fetch origin")
        _run_command(
            steps,
            "git_fetch_origin",
            ["git", "fetch", "origin"],
            cwd=repo_root,
            timeout_seconds=args.timeout_seconds,
        )

        _log("release_preflight: verify main branch")
        _check_branch_exists(steps, cwd=repo_root, timeout_seconds=args.timeout_seconds)

        _log("release_preflight: git switch main")
        switch_proc = _run_command(
            steps,
            "git_switch_main",
            ["git", "switch", "main"],
            cwd=repo_root,
            timeout_seconds=args.timeout_seconds,
            allow_failure=True,
        )
        if switch_proc.returncode != 0:
            steps[-1]["status"] = "fallback"
            steps[-1]["details"]["note"] = "git switch main failed; attempting origin/main"
            _log("release_preflight: git switch -c main --track origin/main")
            _run_command(
                steps,
                "git_switch_main_track",
                ["git", "switch", "-c", "main", "--track", "origin/main"],
                cwd=repo_root,
                timeout_seconds=args.timeout_seconds,
            )

        _log("release_preflight: git pull --ff-only origin main")
        _run_command(
            steps,
            "git_pull_ff_only",
            ["git", "pull", "--ff-only", "origin", "main"],
            cwd=repo_root,
            timeout_seconds=args.timeout_seconds,
        )

        _log("release_preflight: verify main ancestry")
        verify_start = time.perf_counter()
        branch_proc = _run_and_check(
            steps,
            "git_ending_branch",
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root,
            timeout_seconds=args.timeout_seconds,
            check_fn=_check_non_empty("branch"),
        )
        ending_branch = (branch_proc.stdout or "").strip()

        head_proc = _run_and_check(
            steps,
            "git_ending_sha",
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            timeout_seconds=args.timeout_seconds,
            check_fn=_check_non_empty("sha"),
        )
        ending_sha = (head_proc.stdout or "").strip()

        origin_proc = _run_and_check(
            steps,
            "git_origin_main_sha",
            ["git", "rev-parse", "origin/main"],
            cwd=repo_root,
            timeout_seconds=args.timeout_seconds,
            check_fn=_check_non_empty("origin_main_sha"),
        )
        origin_sha = (origin_proc.stdout or "").strip()

        merge_base_proc = _run_command(
            steps,
            "git_merge_base_is_ancestor",
            ["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"],
            cwd=repo_root,
            timeout_seconds=args.timeout_seconds,
            allow_failure=True,
        )
        is_ancestor = merge_base_proc.returncode == 0
        if ending_sha == origin_sha:
            relation = "equal"
        elif is_ancestor:
            relation = "ahead"
        else:
            relation = "diverged"

        matches = ending_branch == "main" and relation in {"equal", "ahead"}
        steps.append(
            {
                "name": "git_verify_main_sync",
                "status": "ok" if matches else "fail",
                "duration": round(time.perf_counter() - verify_start, 4),
                "details": {
                    "head_sha": ending_sha,
                    "origin_main_sha": origin_sha,
                    "is_ancestor": is_ancestor,
                    "relation": relation,
                    "branch": ending_branch,
                },
            }
        )
        if not matches:
            if relation == "diverged":
                print(
                    "Your local main has diverged from origin/main. Update your local history by "
                    "merging/rebasing origin/main into your work (without pushing to main), then "
                    "rerun preflight.",
                    file=sys.stderr,
                )
                custom_error_reported = True
                raise StepFailure(
                    "git_verify_main_sync",
                    "HEAD is not based on origin/main (diverged history). Rebase/merge onto "
                    "origin/main before release.",
                )
            raise StepFailure(
                "git_verify_main_sync",
                "HEAD is not on main",
            )

        _log("release_preflight: verify clean after pull")
        _run_and_check(
            steps,
            "git_status_clean_after",
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            timeout_seconds=args.timeout_seconds,
            check_fn=_check_clean_status,
        )

        _log("release_preflight: run release gate")
        release_gate_cmd = [sys.executable, "-m", "tools.release_gate"]
        if args.strict:
            release_gate_cmd.append("--strict")
        if args.with_network_smoke:
            release_gate_cmd.append("--with-network-smoke")
        release_gate_cmd.extend(["--timeout-seconds", str(args.timeout_seconds)])
        _run_command(
            steps,
            "release_gate",
            release_gate_cmd,
            cwd=repo_root,
            timeout_seconds=args.timeout_seconds,
        )

        overall_status = "pass"
        _log("release_preflight: PASS")
        return_code = 0
    except StepFailure as exc:
        _log(f"release_preflight: FAIL ({exc.step_name})")
        if not dirty_tree_reported and not custom_error_reported:
            print(f"error: {exc.message}", file=sys.stderr)
        return_code = 1
    finally:
        report = {
            "timestamp_utc": started_at,
            "finished_at_utc": _utc_now_iso(),
            "steps": steps,
            "starting_branch": starting_branch,
            "starting_sha": starting_sha,
            "ending_branch": ending_branch,
            "ending_sha": ending_sha,
            "overall_status": overall_status,
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        _log(f"release_preflight: report -> {report_path}")

    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
