from __future__ import annotations

import os
from pathlib import Path

from src.plugins.discovery import PluginCandidate
from src.plugins import validation as validation_mod


def test_demo_plugins_use_inprocess_runtime_on_windows() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    plugin_dir = repo_root / "user_strategies" / "demo_threshold"
    candidate = PluginCandidate(
        plugin_id="demo_threshold",
        plugin_type="strategy",
        plugin_dir=plugin_dir,
        yaml_path=plugin_dir / "strategy.yaml",
        py_path=plugin_dir / "strategy.py",
        extra_files=[],
    )
    expected = os.name == "nt"
    assert validation_mod._should_run_runtime_in_process(candidate) is expected
