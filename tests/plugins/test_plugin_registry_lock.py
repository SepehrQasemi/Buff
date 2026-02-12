from __future__ import annotations

import os
import time
from pathlib import Path

from src.plugins import registry as plugin_registry
from src.plugins.registry import (
    INDEX_LOCK_FILENAME,
    INDEX_LOCK_TTL_SECONDS,
    list_valid_indicators,
)

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


def test_index_rebuild_lock_fail_closed(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()

    indicator_dir = tmp_path / "user_indicators" / "demo_indicator"
    indicator_dir.mkdir(parents=True)
    (indicator_dir / "indicator.yaml").write_text(
        BASE_INDICATOR_YAML,
        encoding="utf-8",
    )
    (indicator_dir / "indicator.py").write_text(
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    return {'value': 1}\n",
        encoding="utf-8",
    )

    lock_path = artifacts_root / "plugin_validation" / INDEX_LOCK_FILENAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("locked", encoding="utf-8")

    indicators = list_valid_indicators(artifacts_root)
    assert indicators == []
    assert not (artifacts_root / "plugin_validation" / "index.json").exists()


def test_index_rebuild_lock_stale_allows_rebuild(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()

    indicator_dir = tmp_path / "user_indicators" / "demo_indicator"
    indicator_dir.mkdir(parents=True)
    (indicator_dir / "indicator.yaml").write_text(
        BASE_INDICATOR_YAML,
        encoding="utf-8",
    )
    (indicator_dir / "indicator.py").write_text(
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    return {'value': 1}\n",
        encoding="utf-8",
    )

    lock_path = artifacts_root / "plugin_validation" / INDEX_LOCK_FILENAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        '{"pid": 1, "created_at_utc": "2000-01-01T00:00:00Z"}',
        encoding="utf-8",
    )

    indicators = list_valid_indicators(artifacts_root)
    assert indicators
    assert indicators[0]["id"] == "demo_indicator"
    assert not lock_path.exists()


def test_index_lock_is_active_does_not_raise(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    lock_path = artifacts_root / "plugin_validation" / INDEX_LOCK_FILENAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    now = plugin_registry._utc_now_iso()
    lock_path.write_text(
        f'{{"pid": 1, "created_at_utc": "{now}"}}',
        encoding="utf-8",
    )

    assert plugin_registry._index_lock_active(artifacts_root) is True


def test_index_lock_invalid_json_stale_mtime_allows_rebuild(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()

    indicator_dir = tmp_path / "user_indicators" / "demo_indicator"
    indicator_dir.mkdir(parents=True)
    (indicator_dir / "indicator.yaml").write_text(
        BASE_INDICATOR_YAML,
        encoding="utf-8",
    )
    (indicator_dir / "indicator.py").write_text(
        "def get_schema():\n    return {}\n\n"
        "def compute(ctx):\n    return {'value': 1}\n",
        encoding="utf-8",
    )

    lock_path = artifacts_root / "plugin_validation" / INDEX_LOCK_FILENAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("{invalid", encoding="utf-8")
    stale_time = time.time() - (INDEX_LOCK_TTL_SECONDS + 5)
    os.utime(lock_path, (stale_time, stale_time))

    indicators = list_valid_indicators(artifacts_root)
    assert indicators
    assert indicators[0]["id"] == "demo_indicator"
    assert not lock_path.exists()
