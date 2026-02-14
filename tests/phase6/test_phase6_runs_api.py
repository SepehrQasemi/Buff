from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app

FIXTURES_ROOT = Path("tests/fixtures/phase6")
GOLDENS_ROOT = Path("tests/goldens/phase6")

SAMPLE_PATH = (FIXTURES_ROOT / "sample.csv").as_posix()
CROSS_PATH = (FIXTURES_ROOT / "cross.csv").as_posix()

REQUIRED_ARTIFACTS = [
    "manifest.json",
    "config.json",
    "metrics.json",
    "equity_curve.json",
    "timeline.json",
    "decision_records.jsonl",
    "trades.jsonl",
    "ohlcv_1m.jsonl",
]

DECIMAL_PATTERN = re.compile(r"-?\d+\.(\d+)")


@pytest.fixture(scope="module")
def phase6_runs(tmp_path_factory):
    runs_root = tmp_path_factory.mktemp("phase6_runs")
    previous = os.environ.get("RUNS_ROOT")
    os.environ["RUNS_ROOT"] = str(runs_root)
    client = TestClient(app)

    response_hold = client.post("/api/v1/runs", json=_payload())
    assert response_hold.status_code in {200, 201}
    run_id_hold = response_hold.json()["run_id"]

    response_cross = client.post(
        "/api/v1/runs",
        json=_payload(
            path=CROSS_PATH,
            strategy={"id": "ma_cross", "params": {"fast_period": 2, "slow_period": 3}},
        ),
    )
    assert response_cross.status_code in {200, 201}
    run_id_cross = response_cross.json()["run_id"]

    try:
        yield {
            "client": client,
            "runs_root": runs_root,
            "hold": run_id_hold,
            "cross": run_id_cross,
        }
    finally:
        client.close()
        if previous is None:
            os.environ.pop("RUNS_ROOT", None)
        else:
            os.environ["RUNS_ROOT"] = previous


def _payload(
    *,
    path: str = SAMPLE_PATH,
    strategy: dict | None = None,
    run_id: str | None = None,
    risk_level: int = 3,
    commission_bps: float = 0.0,
    slippage_bps: float = 0.0,
) -> dict:
    if strategy is None:
        strategy = {"id": "hold", "params": {}}
    payload = {
        "schema_version": "1.0.0",
        "data_source": {
            "type": "csv",
            "path": path,
            "symbol": "BTCUSDT",
            "timeframe": "1m",
        },
        "strategy": strategy,
        "risk": {"level": risk_level},
        "costs": {"commission_bps": commission_bps, "slippage_bps": slippage_bps},
    }
    if run_id:
        payload["run_id"] = run_id
    return payload


def _artifact_hash(run_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted([p for p in run_dir.iterdir() if p.is_file()], key=lambda p: p.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _load_golden_manifest(golden_dir: Path) -> dict:
    return json.loads((golden_dir / "golden_manifest.json").read_text(encoding="utf-8"))


def _assert_decimal_precision(payload: bytes, max_decimals: int) -> None:
    text = payload.decode("utf-8")
    for match in DECIMAL_PATTERN.finditer(text):
        assert len(match.group(1)) <= max_decimals, f"precision exceeded: {match.group(0)}"
    assert "NaN" not in text
    assert "Infinity" not in text


def _assert_error_response(response, status_code: int, code: str) -> dict:
    assert response.status_code == status_code
    payload = response.json()
    assert payload["code"] == code
    assert "message" in payload
    assert "details" in payload
    assert "error" in payload
    error = payload["error"]
    assert error["code"] == code
    assert "message" in error
    assert "details" in error
    return payload


def test_run_create_success(phase6_runs):
    run_id = phase6_runs["hold"]
    run_dir = phase6_runs["runs_root"] / run_id
    assert run_dir.exists()
    for name in REQUIRED_ARTIFACTS:
        assert (run_dir / name).exists()

    registry_path = phase6_runs["runs_root"] / "index.json"
    assert registry_path.exists()
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert any(entry.get("run_id") == run_id for entry in registry.get("runs", []))

    list_response = phase6_runs["client"].get("/api/v1/runs")
    assert list_response.status_code == 200
    listed = list_response.json()
    assert any(entry.get("run_id") == run_id for entry in listed)


def test_run_create_with_upload(monkeypatch):
    runs_root = Path("runs") / "_upload_test"
    if runs_root.exists():
        shutil.rmtree(runs_root, ignore_errors=True)
    runs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))

    client = TestClient(app)
    payload = _payload(path="upload.csv")
    try:
        with open(SAMPLE_PATH, "rb") as handle:
            response = client.post(
                "/api/v1/runs",
                data={"request": json.dumps(payload)},
                files={"file": ("sample.csv", handle, "text/csv")},
            )
        assert response.status_code in {200, 201}
        run_id = response.json()["run_id"]
        run_dir = runs_root / run_id
        assert (run_dir / "metrics.json").exists()
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        source_path = manifest["data"]["source_path"]
        assert source_path.startswith("runs/_upload_test/inputs/")
    finally:
        client.close()
        shutil.rmtree(runs_root, ignore_errors=True)


def test_run_idempotent(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))

    client = TestClient(app)
    first = client.post("/api/v1/runs", json=_payload())
    assert first.status_code == 201
    run_id = first.json()["run_id"]
    run_dir = runs_root / run_id
    before_hash = _artifact_hash(run_dir)

    second = client.post("/api/v1/runs", json=_payload())
    assert second.status_code == 200
    assert second.json()["run_id"] == run_id
    after_hash = _artifact_hash(run_dir)

    assert before_hash == after_hash


def test_run_conflict(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))

    client = TestClient(app)
    run_id = "run_override"
    first = client.post("/api/v1/runs", json=_payload(run_id=run_id, risk_level=3))
    assert first.status_code == 201

    conflict = client.post("/api/v1/runs", json=_payload(run_id=run_id, risk_level=4))
    _assert_error_response(conflict, 409, "RUN_EXISTS")


def test_determinism_across_runs(monkeypatch, tmp_path):
    runs_root_a = tmp_path / "runs_a"
    runs_root_b = tmp_path / "runs_b"

    client = TestClient(app)

    monkeypatch.setenv("RUNS_ROOT", str(runs_root_a))
    first = client.post("/api/v1/runs", json=_payload())
    assert first.status_code == 201
    run_id = first.json()["run_id"]
    hash_a = _artifact_hash(runs_root_a / run_id)

    monkeypatch.setenv("RUNS_ROOT", str(runs_root_b))
    second = client.post("/api/v1/runs", json=_payload())
    assert second.status_code == 201
    run_id_b = second.json()["run_id"]
    assert run_id_b == run_id
    hash_b = _artifact_hash(runs_root_b / run_id_b)

    assert hash_a == hash_b


def test_corrupted_run_detection(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))

    client = TestClient(app)
    response = client.post("/api/v1/runs", json=_payload())
    assert response.status_code == 201
    run_id = response.json()["run_id"]

    metrics_path = runs_root / run_id / "metrics.json"
    metrics_path.unlink()

    listed = client.get("/api/v1/runs")
    assert listed.status_code == 200
    entry = next(entry for entry in listed.json() if entry.get("run_id") == run_id)
    assert entry.get("status") == "CORRUPTED"

    manifest = client.get(f"/api/v1/runs/{run_id}/manifest")
    _assert_error_response(manifest, 409, "RUN_CORRUPTED")


def test_metrics_missing_error_code(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))

    client = TestClient(app)
    response = client.post("/api/v1/runs", json=_payload())
    assert response.status_code == 201
    run_id = response.json()["run_id"]

    metrics_path = runs_root / run_id / "metrics.json"
    metrics_path.unlink()

    metrics = client.get(f"/api/v1/runs/{run_id}/metrics")
    _assert_error_response(metrics, 404, "metrics_missing")


@pytest.mark.parametrize(
    "scenario, run_key",
    [
        ("hold_sample", "hold"),
        ("ma_cross", "cross"),
    ],
)
def test_goldens_match(phase6_runs, scenario, run_key):
    run_id = phase6_runs[run_key]
    run_dir = phase6_runs["runs_root"] / run_id
    golden_dir = GOLDENS_ROOT / scenario
    manifest = _load_golden_manifest(golden_dir)
    expected_artifacts = manifest.get("artifacts", {})

    generated_files = {path.name for path in run_dir.iterdir() if path.is_file()}
    assert generated_files == set(expected_artifacts.keys())

    for name, expected_hash in expected_artifacts.items():
        generated_path = run_dir / name
        golden_path = golden_dir / name
        assert generated_path.exists(), f"missing artifact: {name}"
        assert golden_path.exists(), f"missing golden: {name}"
        generated_bytes = generated_path.read_bytes()
        golden_bytes = golden_path.read_bytes()
        assert generated_bytes == golden_bytes, f"{scenario}/{name} differs"
        assert hashlib.sha256(generated_bytes).hexdigest() == expected_hash


def test_metrics_are_meaningful(phase6_runs):
    run_id = phase6_runs["hold"]
    metrics_path = phase6_runs["runs_root"] / run_id / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert metrics["num_records"] == 1
    assert metrics["num_trades"] == 1
    assert metrics["total_return"] > 0


def test_ma_cross_produces_trade(phase6_runs):
    run_id = phase6_runs["cross"]
    trades_path = phase6_runs["runs_root"] / run_id / "trades.jsonl"
    lines = [line for line in trades_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) >= 1
    record = json.loads(lines[0])
    assert record["side"] == "LONG"


def test_numeric_policy_rounding_and_determinism(monkeypatch, tmp_path):
    runs_root_a = tmp_path / "runs_a"
    runs_root_b = tmp_path / "runs_b"

    client = TestClient(app)
    payload = _payload(slippage_bps=12.3456789)

    monkeypatch.setenv("RUNS_ROOT", str(runs_root_a))
    first = client.post("/api/v1/runs", json=payload)
    assert first.status_code == 201
    run_id = first.json()["run_id"]
    equity_a = (runs_root_a / run_id / "equity_curve.json").read_bytes()
    _assert_decimal_precision(equity_a, 8)

    monkeypatch.setenv("RUNS_ROOT", str(runs_root_b))
    second = client.post("/api/v1/runs", json=payload)
    assert second.status_code == 201
    run_id_b = second.json()["run_id"]
    equity_b = (runs_root_b / run_id_b / "equity_curve.json").read_bytes()
    assert equity_a == equity_b


def test_rejects_path_traversal(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))

    payload = _payload(path="tests/fixtures/phase6/../phase6/sample.csv")
    client = TestClient(app)
    response = client.post("/api/v1/runs", json=payload)
    _assert_error_response(response, 400, "RUN_CONFIG_INVALID")


def test_rejects_absolute_path(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))

    absolute_path = Path(SAMPLE_PATH).resolve()
    payload = _payload(path=str(absolute_path))
    client = TestClient(app)
    response = client.post("/api/v1/runs", json=payload)
    _assert_error_response(response, 400, "RUN_CONFIG_INVALID")


def test_rejects_symlink_escape(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))

    symlink_dir = FIXTURES_ROOT / "_symlink_escape"
    symlink_dir.mkdir(parents=True, exist_ok=True)
    symlink_path = symlink_dir / "escape.csv"
    target = Path.cwd().parent / "outside.csv"

    try:
        if symlink_path.exists() or symlink_path.is_symlink():
            symlink_path.unlink()
        if os.name == "nt":
            os.symlink(str(target), symlink_path, target_is_directory=False)
        else:
            os.symlink(str(target), symlink_path)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink not supported: {exc}")

    try:
        payload = _payload(path=symlink_path.as_posix())
        client = TestClient(app)
        response = client.post("/api/v1/runs", json=payload)
        _assert_error_response(response, 400, "RUN_CONFIG_INVALID")
    finally:
        try:
            symlink_path.unlink()
        except OSError:
            pass
        try:
            symlink_dir.rmdir()
        except OSError:
            pass


def test_error_group_400_invalid_strategy(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))

    payload = _payload(strategy={"id": "unknown", "params": {}})
    client = TestClient(app)
    response = client.post("/api/v1/runs", json=payload)
    _assert_error_response(response, 400, "STRATEGY_INVALID")


def test_error_group_404_run_not_found(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))

    client = TestClient(app)
    response = client.get("/api/v1/runs/missing-run/manifest")
    _assert_error_response(response, 404, "RUN_NOT_FOUND")


def test_error_group_503_registry_lock_timeout(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))

    class _TimeoutLock:
        def __enter__(self):
            raise TimeoutError("REGISTRY_LOCK_TIMEOUT")

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("apps.api.main.lock_registry", lambda _root: _TimeoutLock())

    client = TestClient(app)
    response = client.get("/api/v1/runs")
    _assert_error_response(response, 503, "REGISTRY_LOCK_TIMEOUT")


def test_error_group_500_registry_write_failed(monkeypatch, tmp_path):
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    monkeypatch.setenv("RUNS_ROOT", str(runs_root))

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("apps.api.phase6.run_builder.upsert_registry_entry", _boom)

    client = TestClient(app)
    response = client.post("/api/v1/runs", json=_payload())
    _assert_error_response(response, 500, "REGISTRY_WRITE_FAILED")
