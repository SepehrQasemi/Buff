from __future__ import annotations

import hashlib
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))
os.chdir(REPO_ROOT)

from apps.api.phase6.canonical import write_canonical_json  # noqa: E402
from apps.api.phase6.run_builder import RunBuilderError, create_run  # noqa: E402


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


SCENARIOS = {
    "hold_sample": _payload_hold(),
    "ma_cross": _payload_ma_cross(),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    runs_root = REPO_ROOT / "runs" / "_golden_tmp"
    goldens_root = REPO_ROOT / "tests" / "goldens" / "phase6"

    if runs_root.exists():
        shutil.rmtree(runs_root, ignore_errors=True)
    runs_root.mkdir(parents=True, exist_ok=True)
    os.environ["RUNS_ROOT"] = str(runs_root)

    for scenario, payload in SCENARIOS.items():
        try:
            status_code, response = create_run(payload)
        except RunBuilderError as exc:
            raise SystemExit(f"Failed to create {scenario}: {exc.code} {exc.message}") from exc
        if status_code not in {200, 201}:
            raise SystemExit(f"Failed to create {scenario}: status {status_code}")

        run_id = response["run_id"]
        run_dir = runs_root / run_id
        if not run_dir.exists():
            raise SystemExit(f"Missing run dir for {scenario}")

        scenario_dir = goldens_root / scenario
        if scenario_dir.exists():
            shutil.rmtree(scenario_dir, ignore_errors=True)
        scenario_dir.mkdir(parents=True, exist_ok=True)

        artifact_hashes: dict[str, str] = {}
        for artifact in sorted([p for p in run_dir.iterdir() if p.is_file()], key=lambda p: p.name):
            target = scenario_dir / artifact.name
            shutil.copy2(artifact, target)
            artifact_hashes[artifact.name] = _sha256(target)

        manifest = {"schema_version": "golden.v1", "artifacts": artifact_hashes}
        write_canonical_json(scenario_dir / "golden_manifest.json", manifest)
        print(f"Wrote goldens for {scenario} ({run_id})")

    shutil.rmtree(runs_root, ignore_errors=True)


if __name__ == "__main__":
    main()
