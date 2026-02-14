from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _load_run_builder():
    from apps.api.phase6.run_builder import RunBuilderError, create_run

    return RunBuilderError, create_run


RunBuilderError, create_run = _load_run_builder()

GOLDENS_ROOT = REPO_ROOT / "tests" / "goldens" / "phase6"


def _payload_hold() -> dict:
    return {
        "schema_version": "1.0.0",
        "data_source": {
            "type": "csv",
            "path": "tests/fixtures/phase6/sample.csv",
            "symbol": "BTCUSDT",
            "timeframe": "1m",
        },
        "strategy": {"id": "hold", "params": {}},
        "risk": {"level": 3},
        "costs": {"commission_bps": 0.0, "slippage_bps": 0.0},
    }


def _payload_ma_cross() -> dict:
    return {
        "schema_version": "1.0.0",
        "data_source": {
            "type": "csv",
            "path": "tests/fixtures/phase6/cross.csv",
            "symbol": "BTCUSDT",
            "timeframe": "1m",
        },
        "strategy": {"id": "ma_cross", "params": {"fast_period": 2, "slow_period": 3}},
        "risk": {"level": 3},
        "costs": {"commission_bps": 0.0, "slippage_bps": 0.0},
    }


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _artifact_hashes(run_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted([p for p in run_dir.iterdir() if p.is_file()], key=lambda p: p.name):
        hashes[path.name] = _sha256_bytes(path.read_bytes())
    return hashes


def _load_golden_manifest(scenario: str) -> dict[str, str]:
    manifest_path = GOLDENS_ROOT / scenario / "golden_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return payload.get("artifacts", {})


def _create_run(runs_root: Path, payload: dict) -> tuple[str, Path]:
    os.environ["RUNS_ROOT"] = str(runs_root)
    try:
        status_code, response = create_run(payload)
    except RunBuilderError as exc:
        raise SystemExit(f"Run creation failed: {exc.code} {exc.message}") from exc
    if status_code not in {200, 201}:
        raise SystemExit(f"Run creation failed: status {status_code}")
    run_id = response["run_id"]
    run_dir = runs_root / run_id
    if not run_dir.exists():
        raise SystemExit(f"Run dir missing: {run_dir}")
    return run_id, run_dir


def _verify_registry(runs_root: Path, run_id: str) -> None:
    registry_path = runs_root / "index.json"
    if not registry_path.exists():
        raise SystemExit("Registry missing")
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    runs = payload.get("runs", [])
    entry = next(
        (item for item in runs if isinstance(item, dict) and item.get("run_id") == run_id), None
    )
    if entry is None:
        raise SystemExit(f"Registry entry missing for {run_id}")
    if entry.get("status") == "CORRUPTED":
        raise SystemExit(f"Registry entry corrupted for {run_id}")
    manifest_path = entry.get("manifest_path")
    if manifest_path != f"{run_id}/manifest.json":
        raise SystemExit(f"Registry manifest path invalid for {run_id}")


def _verify_goldens(scenario: str, run_dir: Path) -> None:
    expected = _load_golden_manifest(scenario)
    if not expected:
        raise SystemExit(f"Golden manifest missing artifacts for {scenario}")
    for name, expected_hash in expected.items():
        artifact_path = run_dir / name
        golden_path = GOLDENS_ROOT / scenario / name
        if not artifact_path.exists():
            raise SystemExit(f"Artifact missing: {name}")
        if not golden_path.exists():
            raise SystemExit(f"Golden missing: {name}")
        data = artifact_path.read_bytes()
        if data != golden_path.read_bytes():
            raise SystemExit(f"Golden mismatch: {scenario}/{name}")
        if _sha256_bytes(data) != expected_hash:
            raise SystemExit(f"Golden hash mismatch: {scenario}/{name}")


def main() -> int:
    repo_root = REPO_ROOT
    os.chdir(repo_root)

    base_root = repo_root / "runs" / "_phase6_release_gate"
    root_a = base_root / "A"
    root_b = base_root / "B"
    if base_root.exists():
        shutil.rmtree(base_root, ignore_errors=True)
    root_a.mkdir(parents=True, exist_ok=True)
    root_b.mkdir(parents=True, exist_ok=True)

    try:
        run_id_a, run_dir_a = _create_run(root_a, _payload_hold())
        run_id_b, run_dir_b = _create_run(root_b, _payload_hold())
        if run_id_a != run_id_b:
            raise SystemExit("Determinism failed: run_id mismatch")

        hashes_a = _artifact_hashes(run_dir_a)
        hashes_b = _artifact_hashes(run_dir_b)
        if hashes_a != hashes_b:
            raise SystemExit("Determinism failed: artifact hashes differ")

        _verify_registry(root_a, run_id_a)
        _verify_registry(root_b, run_id_b)

        _, run_dir_cross = _create_run(root_a, _payload_ma_cross())
        _verify_goldens("hold_sample", run_dir_a)
        _verify_goldens("ma_cross", run_dir_cross)
    finally:
        shutil.rmtree(base_root, ignore_errors=True)

    print("phase6_release_gate: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
