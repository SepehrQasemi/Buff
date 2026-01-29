from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


ALLOWED_INPUTS = {"open", "high", "low", "close", "volume"}


@dataclass(frozen=True)
class IndicatorSpec:
    name: str
    inputs: list[str]
    params_schema: dict[str, object]
    version: int


def validate_indicator(spec: IndicatorSpec) -> None:
    if not spec.name:
        raise ValueError("indicator_name_required")
    if not spec.inputs:
        raise ValueError("indicator_inputs_required")
    for value in spec.inputs:
        if value not in ALLOWED_INPUTS:
            raise ValueError("indicator_invalid_input")
    if spec.version <= 0:
        raise ValueError("indicator_version_required")


def write_sandbox_indicator(workspace: str, spec: IndicatorSpec, code: str) -> Path:
    root = Path("workspaces").resolve()
    base_resolved = (root / workspace / "indicators").resolve()
    if root not in base_resolved.parents and base_resolved != root:
        raise ValueError("invalid_workspace")
    base_resolved.mkdir(parents=True, exist_ok=True)
    path = base_resolved / f"{spec.name}_v{spec.version}.json"
    payload = {"spec": asdict(spec), "code": code}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def approve_indicator(sandbox_path: Path, registry_dir: Path) -> Path:
    registry_dir.mkdir(parents=True, exist_ok=True)
    payload = json.loads(sandbox_path.read_text(encoding="utf-8"))
    spec = payload.get("spec", {})
    name = spec.get("name", "unknown")
    version = spec.get("version", 0)
    registry_path = registry_dir / f"{name}_v{version}.json"
    registry_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return registry_path
