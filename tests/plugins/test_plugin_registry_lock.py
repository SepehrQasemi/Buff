from __future__ import annotations

import json
import os
import time
from pathlib import Path

from src.plugins import registry as plugin_registry
from src.plugins.registry import INDEX_LOCK_FILENAME, INDEX_LOCK_TTL_SECONDS, list_valid_indicators


def _write_artifact(artifacts_root: Path, plugin_id: str) -> None:
    payload = {
        "plugin_type": "indicator",
        "id": plugin_id,
        "status": "VALID",
        "reason_codes": [],
        "reason_messages": [],
        "checked_at_utc": "2026-02-01T00:00:00Z",
        "source_hash": "deadbeef",
        "name": "Demo",
        "version": "1.0.0",
        "category": "momentum",
    }
    path = artifacts_root / "plugin_validation" / "indicator" / f"{plugin_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_index_rebuild_lock_fail_closed(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()

    lock_path = artifacts_root / "plugin_validation" / INDEX_LOCK_FILENAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("locked", encoding="utf-8")

    indicators = list_valid_indicators(artifacts_root)
    assert indicators == []
    assert not (artifacts_root / "plugin_validation" / "index.json").exists()


def test_index_rebuild_lock_stale_allows_rebuild(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    _write_artifact(artifacts_root, "demo_indicator")

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
    _write_artifact(artifacts_root, "demo_indicator")

    lock_path = artifacts_root / "plugin_validation" / INDEX_LOCK_FILENAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("{invalid", encoding="utf-8")
    stale_time = time.time() - (INDEX_LOCK_TTL_SECONDS + 5)
    os.utime(lock_path, (stale_time, stale_time))

    indicators = list_valid_indicators(artifacts_root)
    assert indicators
    assert indicators[0]["id"] == "demo_indicator"
    assert not lock_path.exists()
