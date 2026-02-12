from __future__ import annotations

import json
from pathlib import Path

from src.plugins.discovery import discover_plugins
from src.plugins.registry import list_valid_indicators
from src.plugins.validation import validate_all

BASE_INDICATOR_YAML = """\
id: demo_indicator
name: Demo
version: 1.0.0
category: momentum
inputs: [close]
outputs: [value]
params: []
warmup_bars: 1
nan_policy: propagate
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _setup_indicator(tmp_path: Path, plugin_id: str) -> Path:
    plugin_dir = tmp_path / "user_indicators" / plugin_id
    _write(plugin_dir / "indicator.yaml", BASE_INDICATOR_YAML.replace("demo_indicator", plugin_id))
    _write(
        plugin_dir / "indicator.py",
        "def get_schema():\n    return {}\n\ndef compute(ctx):\n    return {'value': 1}\n",
    )
    return plugin_dir


def test_index_corruption_triggers_rebuild(tmp_path: Path) -> None:
    _setup_indicator(tmp_path, "rsi")
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()

    index_path = artifacts_root / "plugin_validation" / "index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("{", encoding="utf-8")

    active = list_valid_indicators(artifacts_root)
    assert active
    assert active[0]["id"] == "rsi"

    payload = json.loads(index_path.read_text(encoding="utf-8"))
    assert payload.get("total_plugins") == 1


def test_hash_change_triggers_rebuild(tmp_path: Path) -> None:
    plugin_dir = _setup_indicator(tmp_path, "rsi")
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()

    candidates = discover_plugins(tmp_path)
    validate_all(candidates, artifacts_root / "plugin_validation")

    artifact_path = artifacts_root / "plugin_validation" / "indicator" / "rsi.json"
    original = json.loads(artifact_path.read_text(encoding="utf-8"))
    original_hash = original.get("source_hash")

    _write(
        plugin_dir / "indicator.py",
        "def get_schema():\n    return {}\n\ndef compute(ctx):\n    return {'value': 2}\n",
    )

    list_valid_indicators(artifacts_root)

    updated = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert updated.get("source_hash") != original_hash


def test_missing_artifact_triggers_rebuild(tmp_path: Path) -> None:
    _setup_indicator(tmp_path, "rsi")
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()

    candidates = discover_plugins(tmp_path)
    validate_all(candidates, artifacts_root / "plugin_validation")

    artifact_path = artifacts_root / "plugin_validation" / "indicator" / "rsi.json"
    assert artifact_path.exists()
    artifact_path.unlink()

    active = list_valid_indicators(artifacts_root)
    assert active
    assert active[0]["id"] == "rsi"
    assert artifact_path.exists()


def test_missing_artifact_rebuild_fail_closed(tmp_path: Path, monkeypatch) -> None:
    _setup_indicator(tmp_path, "rsi")
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()

    candidates = discover_plugins(tmp_path)
    validate_all(candidates, artifacts_root / "plugin_validation")

    artifact_path = artifacts_root / "plugin_validation" / "indicator" / "rsi.json"
    artifact_path.unlink()

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("src.plugins.registry.validate_all", boom)
    active = list_valid_indicators(artifacts_root)
    assert active == []


def test_corrupt_index_rebuild_fail_closed(tmp_path: Path, monkeypatch) -> None:
    _setup_indicator(tmp_path, "rsi")
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()

    index_path = artifacts_root / "plugin_validation" / "index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("{", encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("src.plugins.registry.validate_all", boom)
    active = list_valid_indicators(artifacts_root)
    assert active == []
