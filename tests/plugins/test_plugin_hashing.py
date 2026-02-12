from __future__ import annotations

from pathlib import Path

from src.plugins import validation as validation_module


def _hash_dir(path: Path) -> str:
    issues: list[validation_module.ValidationIssue] = []
    return validation_module._hash_plugin_dir(path, issues)


def test_hash_stable_across_file_order(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "user_indicators" / "demo"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "a.txt").write_text("alpha", encoding="utf-8")
    (plugin_dir / "b.txt").write_text("bravo", encoding="utf-8")
    initial = _hash_dir(plugin_dir)

    (plugin_dir / "a.txt").unlink()
    (plugin_dir / "b.txt").unlink()
    (plugin_dir / "b.txt").write_text("bravo", encoding="utf-8")
    (plugin_dir / "a.txt").write_text("alpha", encoding="utf-8")
    reordered = _hash_dir(plugin_dir)

    assert initial == reordered


def test_hash_changes_on_content_change(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "user_indicators" / "demo"
    plugin_dir.mkdir(parents=True)
    target = plugin_dir / "indicator.py"
    target.write_text("print('a')", encoding="utf-8")
    first = _hash_dir(plugin_dir)

    target.write_text("print('b')", encoding="utf-8")
    second = _hash_dir(plugin_dir)

    assert first != second


def test_hash_changes_on_new_file(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "user_indicators" / "demo"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "indicator.py").write_text("print('a')", encoding="utf-8")
    first = _hash_dir(plugin_dir)

    (plugin_dir / "extra.txt").write_text("extra", encoding="utf-8")
    second = _hash_dir(plugin_dir)

    assert first != second
