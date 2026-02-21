from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.phase6 import experiment_builder as s7_builder
from apps.api.phase6.experiment_contract import MAX_EXPERIMENT_CANDIDATES

TEST_USER_ID = "test-user"
SAMPLE_PATH = Path("tests/fixtures/phase6/sample.csv").as_posix()
CROSS_PATH = Path("tests/fixtures/phase6/cross.csv").as_posix()


def _user_root(runs_root: Path) -> Path:
    return runs_root / "users" / TEST_USER_ID


def _experiments_root(runs_root: Path) -> Path:
    return _user_root(runs_root) / "experiments"


def _run_payload(*, path: str, strategy: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "data_source": {
            "type": "csv",
            "path": path,
            "symbol": "BTCUSDT",
            "timeframe": "1m",
        },
        "strategy": strategy,
        "risk": {"level": 3},
        "costs": {"commission_bps": 0.0, "slippage_bps": 0.0},
    }


@pytest.fixture
def experiment_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    runs_root = tmp_path / "runs_root"
    runs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("BUFF_DEFAULT_USER", TEST_USER_ID)
    return runs_root


def test_s7_experiment_caps_too_many_candidates(experiment_env: Path) -> None:
    payload = {
        "schema_version": "1.0.0",
        "name": "s7-cap-test",
        "candidates": [
            {
                "candidate_id": f"cand_{index + 1:03d}",
                "run_config": _run_payload(path=SAMPLE_PATH, strategy={"id": "hold", "params": {}}),
            }
            for index in range(MAX_EXPERIMENT_CANDIDATES + 1)
        ],
    }

    with TestClient(app) as client:
        response = client.post("/api/v1/experiments", json=payload)

    assert response.status_code == 400
    error_payload = response.json()
    assert error_payload["code"] == "EXPERIMENT_CANDIDATES_LIMIT_EXCEEDED"
    assert error_payload["details"]["requested_count"] == MAX_EXPERIMENT_CANDIDATES + 1
    assert error_payload["details"]["max_allowed"] == MAX_EXPERIMENT_CANDIDATES
    assert error_payload["error_envelope"]["error_code"] == "EXPERIMENT_CANDIDATES_LIMIT_EXCEEDED"
    assert "Traceback" not in json.dumps(error_payload, sort_keys=True)


def test_s7_experiment_concurrency_lock(
    experiment_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_create_run = s7_builder.create_run

    def delayed_create_run(payload: dict[str, object], *, user_id: str | None = None):
        # Hold the experiment lock long enough for a competing request to hit timeout.
        time.sleep(0.2)
        return original_create_run(payload, user_id=user_id)

    monkeypatch.setattr(s7_builder, "create_run", delayed_create_run)
    monkeypatch.setattr(s7_builder, "_EXPERIMENT_LOCK_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(s7_builder, "_EXPERIMENT_LOCK_POLL_SECONDS", 0.005)

    payload = {
        "schema_version": "1.0.0",
        "name": "s7-lock-test",
        "candidates": [
            {
                "candidate_id": "hold_a",
                "run_config": _run_payload(path=SAMPLE_PATH, strategy={"id": "hold", "params": {}}),
            },
            {
                "candidate_id": "cross_b",
                "run_config": _run_payload(
                    path=CROSS_PATH,
                    strategy={"id": "ma_cross", "params": {"fast_period": 2, "slow_period": 3}},
                ),
            },
        ],
    }

    barrier = threading.Barrier(2)

    def submit_once():
        barrier.wait(timeout=5.0)
        return s7_builder.create_experiment(payload, user_id=TEST_USER_ID)

    successes: list[tuple[int, dict[str, object]]] = []
    failures: list[BaseException] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit_once) for _ in range(2)]
        for future in futures:
            try:
                successes.append(future.result(timeout=10.0))
            except BaseException as exc:  # pragma: no cover - explicit failure capture path.
                failures.append(exc)

    assert len(successes) == 1
    assert len(failures) == 1

    status_code, response_payload = successes[0]
    assert status_code == 201
    experiment_id = str(response_payload["experiment_id"])

    failure = failures[0]
    assert isinstance(failure, s7_builder.ExperimentBuilderError)
    assert failure.code == "EXPERIMENT_LOCK_TIMEOUT"

    experiment_dir = _experiments_root(experiment_env) / experiment_id
    manifest = json.loads((experiment_dir / "experiment_manifest.json").read_text(encoding="utf-8"))
    comparison = json.loads(
        (experiment_dir / "comparison_summary.json").read_text(encoding="utf-8")
    )
    assert manifest["experiment_id"] == experiment_id
    assert comparison["experiment_id"] == experiment_id
    assert manifest["summary"]["succeeded"] == comparison["counts"]["succeeded"]
    assert manifest["summary"]["failed"] == comparison["counts"]["failed"]
    assert isinstance(comparison.get("rows"), list)


def test_write_json_atomic_writes_complete_json(tmp_path: Path) -> None:
    target = tmp_path / "atomic" / "artifact.json"
    for idx in range(5):
        payload = {
            "schema_version": "1.0.0",
            "iteration": idx,
            "items": [{"index": idx}, {"index": idx + 1}],
        }
        s7_builder.write_json_atomic(target, payload)
        loaded = json.loads(target.read_text(encoding="utf-8"))
        assert loaded == payload

    leftovers = sorted(target.parent.glob(f".{target.name}.tmp-*"))
    assert leftovers == []
