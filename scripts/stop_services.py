from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _orchestrator import (  # noqa: E402
    is_buff_api_process,
    is_buff_next_process,
    kill_pid_tree,
    list_processes,
    pidfile_path,
    read_pidfile,
)


def _log(message: str) -> None:
    print(message, flush=True)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    pid_path = pidfile_path(repo_root)
    killed: list[str] = []

    if pid_path.exists():
        data = read_pidfile(pid_path) or {}
        for label in ("api", "ui"):
            entry = data.get(label, {})
            pid = entry.get("pid")
            if not pid:
                continue
            try:
                kill_pid_tree(int(pid), label.upper())
                killed.append(f"{label}:{pid}")
            except (TypeError, ValueError):
                continue
        pid_path.unlink(missing_ok=True)
    else:
        for proc in list_processes():
            if is_buff_api_process(proc, repo_root):
                try:
                    kill_pid_tree(int(proc.get("pid", "0")), "API")
                    killed.append(f"api:{proc.get('pid')}")
                except (TypeError, ValueError):
                    continue
            elif is_buff_next_process(proc, repo_root):
                try:
                    kill_pid_tree(int(proc.get("pid", "0")), "UI")
                    killed.append(f"ui:{proc.get('pid')}")
                except (TypeError, ValueError):
                    continue

    if killed:
        _log("Stopped Buff services: " + ", ".join(killed))
    else:
        _log("No Buff services found to stop.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
