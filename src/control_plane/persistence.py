from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .state import ControlState, Environment, SystemState


def _default_path() -> Path:
    return Path(".buff") / "control_state.json"


def save_state(state: ControlState, path: Path | None = None) -> None:
    path = path or _default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(state)
    payload["state"] = state.state.value
    payload["environment"] = state.environment.value
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    tmp_path.replace(path)


def load_state(path: Path | None = None) -> ControlState:
    path = path or _default_path()
    if not path.exists():
        return ControlState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ControlState(reason="state_load_error")
    try:
        return ControlState(
            state=SystemState(data.get("state", SystemState.DISARMED.value)),
            environment=Environment(data.get("environment", Environment.PAPER.value)),
            approvals=set(data.get("approvals", [])),
            reason=data.get("reason"),
        )
    except Exception:
        return ControlState(reason="state_load_error")
