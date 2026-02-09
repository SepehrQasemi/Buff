from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal

PluginType = Literal["indicator", "strategy"]


@dataclass(frozen=True)
class PluginCandidate:
    plugin_id: str
    plugin_type: PluginType
    yaml_path: Path
    py_path: Path
    fingerprint: str


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
            fingerprint = _fingerprint_files(yaml_path, py_path)
            candidates.append(
                PluginCandidate(
                    plugin_id=entry.name,
                    plugin_type=plugin_type,
                    yaml_path=yaml_path,
                    py_path=py_path,
                    fingerprint=fingerprint,
                )
            )
    return candidates


def _fingerprint_files(yaml_path: Path, py_path: Path) -> str:
    yaml_bytes = _read_bytes(yaml_path)
    py_bytes = _read_bytes(py_path)
    return sha256(yaml_bytes + py_bytes).hexdigest()


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        return b""
