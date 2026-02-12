from __future__ import annotations

from pathlib import Path

import pytest

from src.plugins import validation as validation_module
from src.plugins.validation import ValidationResult


def _sample_result() -> ValidationResult:
    return ValidationResult(
        plugin_id="demo",
        plugin_type="indicator",
        name=None,
        version=None,
        category=None,
        status="VALID",
        issues=[],
        checked_at_utc="2026-02-01T00:00:00Z",
        source_hash="deadbeef",
        warnings=[],
    )


def _patch_write_failure(monkeypatch: pytest.MonkeyPatch, temp_path: Path) -> None:
    original = Path.write_text

    def boom(self: Path, data: str, encoding="utf-8", errors=None, newline=None):
        if self == temp_path:
            original(self, data[:5], encoding=encoding, errors=errors, newline=newline)
            raise OSError("boom")
        return original(self, data, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(Path, "write_text", boom)


@pytest.mark.parametrize("mode", ["artifact", "index"])
def test_atomic_write_preserves_dest_on_write_failure(tmp_path, monkeypatch, mode):
    out_dir = tmp_path / "artifacts" / "plugin_validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    result = _sample_result()

    if mode == "artifact":
        dest = out_dir / "indicator" / "demo.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        writer = lambda: validation_module.write_validation_artifact(result, out_dir)  # noqa: E731
    else:
        dest = out_dir / "index.json"
        writer = lambda: validation_module.write_validation_index([result], out_dir)  # noqa: E731

    dest.write_text("original", encoding="utf-8")
    original = dest.read_text(encoding="utf-8")
    temp = dest.with_suffix(dest.suffix + ".tmp")

    _patch_write_failure(monkeypatch, temp)

    with pytest.raises(OSError):
        writer()

    assert dest.read_text(encoding="utf-8") == original
    assert not temp.exists()


@pytest.mark.parametrize("mode", ["artifact", "index"])
def test_atomic_write_preserves_dest_on_replace_failure(tmp_path, monkeypatch, mode):
    out_dir = tmp_path / "artifacts" / "plugin_validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    result = _sample_result()

    if mode == "artifact":
        dest = out_dir / "indicator" / "demo.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        writer = lambda: validation_module.write_validation_artifact(result, out_dir)  # noqa: E731
    else:
        dest = out_dir / "index.json"
        writer = lambda: validation_module.write_validation_index([result], out_dir)  # noqa: E731

    dest.write_text("original", encoding="utf-8")
    original = dest.read_text(encoding="utf-8")
    temp = dest.with_suffix(dest.suffix + ".tmp")

    def boom(_src, _dst):
        raise OSError("boom")

    monkeypatch.setattr(validation_module.os, "replace", boom)

    with pytest.raises(OSError):
        writer()

    assert dest.read_text(encoding="utf-8") == original
    assert not temp.exists()
