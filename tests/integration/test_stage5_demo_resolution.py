from __future__ import annotations

from pathlib import Path

from apps.api.artifacts import discover_runs, resolve_run_dir


def test_stage5_demo_resolves_from_artifacts_root(monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    artifacts_root = repo_root / "tests" / "fixtures" / "artifacts"
    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))

    run_dir = resolve_run_dir("stage5_demo", artifacts_root)
    assert run_dir == (artifacts_root / "stage5_demo").resolve()

    run_ids = {entry.get("id") for entry in discover_runs() if isinstance(entry, dict)}
    assert "stage5_demo" in run_ids
