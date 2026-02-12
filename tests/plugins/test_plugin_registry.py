from __future__ import annotations

import json
from pathlib import Path

from src.plugins import registry as plugin_registry
from src.plugins.registry import list_invalid_indicators, list_valid_indicators


def _write_artifact(
    root: Path,
    plugin_type: str,
    plugin_id: str,
    status: str,
    *,
    reason_codes: list[str] | None = None,
    reason_messages: list[str] | None = None,
    name: str = "Demo",
    version: str = "1.0.0",
    category: str = "momentum",
) -> None:
    payload = {
        "plugin_type": plugin_type,
        "id": plugin_id,
        "status": status,
        "reason_codes": reason_codes or [],
        "reason_messages": reason_messages or [],
        "checked_at_utc": "2026-02-01T00:00:00Z",
        "source_hash": "deadbeef",
        "name": name,
        "version": version,
        "category": category,
    }
    path = root / plugin_type / f"{plugin_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_index_corruption_rebuilds_from_artifacts(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    plugins_root = artifacts_root / "plugin_validation"
    _write_artifact(plugins_root, "indicator", "rsi", "VALID", name="RSI")

    index_path = plugins_root / "index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("{", encoding="utf-8")

    active = list_valid_indicators(artifacts_root)
    assert active
    assert active[0]["id"] == "rsi"

    payload = json.loads(index_path.read_text(encoding="utf-8"))
    assert payload.get("total_plugins") == 1


def test_missing_artifact_hides_plugin(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    plugins_root = artifacts_root / "plugin_validation"
    _write_artifact(plugins_root, "indicator", "rsi", "VALID", name="RSI")

    active = list_valid_indicators(artifacts_root)
    assert active

    artifact_path = plugins_root / "indicator" / "rsi.json"
    artifact_path.unlink()

    active = list_valid_indicators(artifacts_root)
    assert active == []


def test_invalid_plugin_never_listed_as_valid(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    plugins_root = artifacts_root / "plugin_validation"
    _write_artifact(
        plugins_root,
        "indicator",
        "bad",
        "INVALID",
        reason_codes=["FORBIDDEN_IMPORT:os"],
        reason_messages=["Import 'os' is not allowed."],
    )

    active = list_valid_indicators(artifacts_root)
    assert active == []
    failed = list_invalid_indicators(artifacts_root)
    assert failed
    assert failed[0]["id"] == "bad"


def test_registry_rejects_path_escape_ids(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    plugins_root = artifacts_root / "plugin_validation"
    plugins_root.mkdir(parents=True, exist_ok=True)

    index_payload = {
        "index_built_at": "2026-02-01T00:00:00Z",
        "total_plugins": 1,
        "total_valid": 1,
        "total_invalid": 0,
        "plugins": {
            "indicator:../escape": {
                "id": "../escape",
                "plugin_type": "indicator",
                "status": "VALID",
                "source_hash": "deadbeef",
                "checked_at_utc": "2026-02-01T00:00:00Z",
                "name": "Escape",
                "version": "1.0.0",
                "category": "momentum",
            }
        },
    }
    index_payload["content_hash"] = plugin_registry._compute_index_content_hash(index_payload)
    (plugins_root / "index.json").write_text(json.dumps(index_payload), encoding="utf-8")

    active = list_valid_indicators(artifacts_root)
    assert active == []

    failed = list_invalid_indicators(artifacts_root)
    assert failed
    assert failed[0]["id"] == "../escape"
    assert failed[0]["errors"][0]["rule_id"] == "ARTIFACT_INVALID"


def test_registry_does_not_execute_plugin_code(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    plugins_root = artifacts_root / "plugin_validation"
    _write_artifact(plugins_root, "indicator", "sneaky", "VALID", name="Sneaky")

    plugin_dir = tmp_path / "user_indicators" / "sneaky"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "indicator.yaml").write_text(
        "\n".join(
            [
                "id: sneaky",
                "name: Sneaky",
                "version: 1.0.0",
                "category: momentum",
                "inputs: [close]",
                "outputs: [value]",
                "params: []",
                "warmup_bars: 1",
                "nan_policy: propagate",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (plugin_dir / "indicator.py").write_text(
        "raise RuntimeError('should not import')\n",
        encoding="utf-8",
    )

    active = list_valid_indicators(artifacts_root)
    assert active
    assert active[0]["id"] == "sneaky"
