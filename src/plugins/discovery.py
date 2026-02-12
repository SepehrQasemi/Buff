from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

PluginType = Literal["indicator", "strategy"]


@dataclass(frozen=True)
class PluginCandidate:
    plugin_id: str
    plugin_type: PluginType
    plugin_dir: Path
    yaml_path: Path
    py_path: Path
    extra_files: list[str]


def discover_plugins(root: Path) -> list[PluginCandidate]:
    root_path = Path(root)
    candidates: list[PluginCandidate] = []
    specs = [
        ("indicator", "user_indicators", "indicator.yaml", "indicator.py"),
        ("strategy", "user_strategies", "strategy.yaml", "strategy.py"),
    ]
    for plugin_type, folder, yaml_name, py_name in specs:
        base = root_path / folder
        if not base.is_dir():
            continue
        for entry in sorted(base.iterdir(), key=lambda p: p.name):
            if not entry.is_dir():
                continue
            yaml_path = entry / yaml_name
            py_path = entry / py_name
            if not (yaml_path.exists() or py_path.exists()):
                continue
            extra_files = _extra_top_level_files(entry, {yaml_name, py_name})
            candidates.append(
                PluginCandidate(
                    plugin_id=entry.name,
                    plugin_type=plugin_type,
                    plugin_dir=entry,
                    yaml_path=yaml_path,
                    py_path=py_path,
                    extra_files=extra_files,
                )
            )
    return candidates


def _extra_top_level_files(plugin_dir: Path, required: set[str]) -> list[str]:
    allowed = set(required) | {"README.md", "README.txt"}
    extras: list[str] = []
    for entry in sorted(plugin_dir.iterdir(), key=lambda p: p.name):
        if entry.is_file() and entry.name not in allowed:
            extras.append(entry.name)
    return extras
