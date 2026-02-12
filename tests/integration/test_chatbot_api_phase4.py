from pathlib import Path
import shutil

from fastapi.testclient import TestClient
import yaml

from apps.api.main import app


def _file_map(files):
    return {item["path"]: item["contents"] for item in files}


def _write(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def test_chat_modes():
    client = TestClient(app)
    response = client.get("/api/v1/chat/modes")
    assert response.status_code == 200
    payload = response.json()
    modes = {item["mode"] for item in payload.get("modes", [])}
    assert "add_indicator" in modes
    assert "add_strategy" in modes
    assert "review_plugin" in modes
    assert "troubleshoot_errors" in modes
    assert "explain_trade" in modes


def test_add_indicator_template():
    client = TestClient(app)
    response = client.post(
        "/api/v1/chat",
        json={
            "mode": "add_indicator",
            "message": "add indicator",
            "context": {
                "indicator_id": "demo_rsi",
                "name": "Demo RSI",
                "inputs": ["close"],
                "outputs": ["rsi"],
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "add_indicator"
    assert data["summary"]
    assert isinstance(data["steps"], list)
    files = _file_map(data["files_to_create"])
    assert "user_indicators/demo_rsi/indicator.yaml" in files
    assert "user_indicators/demo_rsi/indicator.py" in files

    indicator_yaml = yaml.safe_load(files["user_indicators/demo_rsi/indicator.yaml"])
    for field in [
        "id",
        "name",
        "version",
        "category",
        "inputs",
        "outputs",
        "params",
        "warmup_bars",
        "nan_policy",
    ]:
        assert field in indicator_yaml

    indicator_py = files["user_indicators/demo_rsi/indicator.py"]
    assert "def compute" in indicator_py


def test_add_strategy_template():
    client = TestClient(app)
    response = client.post(
        "/api/v1/chat",
        json={
            "mode": "add_strategy",
            "message": "add strategy",
            "context": {
                "strategy_id": "demo_cross",
                "name": "Demo Cross",
                "inputs": ["close"],
                "indicators": ["rsi"],
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "add_strategy"
    assert data["summary"]
    assert isinstance(data["steps"], list)
    files = _file_map(data["files_to_create"])
    assert "user_strategies/demo_cross/strategy.yaml" in files
    assert "user_strategies/demo_cross/strategy.py" in files

    strategy_yaml = yaml.safe_load(files["user_strategies/demo_cross/strategy.yaml"])
    for field in [
        "id",
        "name",
        "version",
        "category",
        "warmup_bars",
        "inputs",
        "params",
        "outputs",
    ]:
        assert field in strategy_yaml
    assert "def on_bar" in files["user_strategies/demo_cross/strategy.py"]


def test_explain_trade_missing_artifacts():
    client = TestClient(app)
    response = client.post(
        "/api/v1/chat",
        json={
            "mode": "explain_trade",
            "message": "explain trade",
            "context": {"run_id": "missing-run", "trade_id": "trade-1"},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "insufficient_artifacts" in data["blockers"]
    assert data["files_to_create"] == []


def test_explain_trade_invalid_run_id_parent():
    client = TestClient(app)
    response = client.post(
        "/api/v1/chat",
        json={
            "mode": "explain_trade",
            "message": "explain trade",
            "context": {"run_id": "../..", "trade_id": "trade-1"},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "invalid_run_id" in data["blockers"]
    assert data["files_to_create"] == []


def test_explain_trade_invalid_run_id_separators():
    client = TestClient(app)
    for invalid_id in ("a/b", "a\\b"):
        response = client.post(
            "/api/v1/chat",
            json={
                "mode": "explain_trade",
                "message": "explain trade",
                "context": {"run_id": invalid_id, "trade_id": "trade-1"},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "invalid_run_id" in data["blockers"]
        assert data["files_to_create"] == []


def test_explain_trade_valid_run_id_missing_artifacts():
    client = TestClient(app)
    response = client.post(
        "/api/v1/chat",
        json={
            "mode": "explain_trade",
            "message": "explain trade",
            "context": {"run_id": "abc123", "trade_id": "trade-1"},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "invalid_run_id" not in data["blockers"]
    assert "insufficient_artifacts" in data["blockers"]
    assert data["files_to_create"] == []


def test_troubleshoot_errors_flow():
    client = TestClient(app)
    response = client.post(
        "/api/v1/chat",
        json={
            "mode": "troubleshoot_errors",
            "message": "help",
            "context": {
                "error_text": "forbidden_import: os\nmissing_field: warmup_bars",
                "plugin_type": "indicator",
                "plugin_id": "demo_review",
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "troubleshoot_errors"
    step_ids = {item["id"] for item in data.get("steps", [])}
    assert "root_causes" in step_ids
    assert "exact_edits" in step_ids
    assert "rerun_commands" in step_ids
    assert "ui_success" in step_ids
    assert any("src.plugins.validate" in cmd for cmd in data.get("commands", []))
    assert any("UI" in item or "Plugin" in item for item in data.get("success_criteria", []))


def test_review_plugin_includes_warmup_nan_and_overfit_sections():
    client = TestClient(app)
    repo_root = Path(__file__).resolve().parents[2]
    plugin_dir = repo_root / "tests" / "tmp_chatbot_review" / "user_indicators" / "demo_review"
    yaml_path = plugin_dir / "indicator.yaml"
    py_path = plugin_dir / "indicator.py"
    try:
        _write(
            yaml_path,
            "\n".join(
                [
                    "id: demo_review",
                    "name: Demo Review",
                    "version: 1.0.0",
                    "category: momentum",
                    "inputs:",
                    "  - close",
                    "outputs:",
                    "  - value",
                    "params:",
                    "  - name: length",
                    "    type: int",
                    "    default: 14",
                    "    min: 2",
                    "    max: 200",
                    "    description: length",
                    "  - name: threshold",
                    "    type: float",
                    "    default: 0.1",
                    "    min: 0.0",
                    "    max: 1.0",
                    "    description: threshold",
                    "  - name: offset",
                    "    type: int",
                    "    default: 3",
                    "    min: 0",
                    "    max: 10",
                    "    description: offset",
                    "  - name: alpha",
                    "    type: float",
                    "    default: 0.5",
                    "    min: 0.0",
                    "    max: 1.0",
                    "    description: alpha",
                    "  - name: beta",
                    "    type: float",
                    "    default: 0.25",
                    "    min: 0.0",
                    "    max: 1.0",
                    "    description: beta",
                    "  - name: gamma",
                    "    type: float",
                    "    default: 0.75",
                    "    min: 0.0",
                    "    max: 1.0",
                    "    description: gamma",
                    "warmup_bars: 0",
                    "nan_policy: fill",
                    "",
                ]
            ),
        )
        _write(
            py_path,
            "\n".join(
                [
                    "def get_schema():",
                    "    return {}",
                    "",
                    "",
                    "def compute(ctx):",
                    "    value = 0.1234",
                    '    return {"value": value}',
                    "",
                ]
            ),
        )
        relative_path = plugin_dir.relative_to(repo_root).as_posix()
        response = client.post(
            "/api/v1/chat",
            json={
                "mode": "review_plugin",
                "message": "review plugin",
                "context": {
                    "kind": "indicator",
                    "id": "demo_review",
                    "path_optional": relative_path,
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        step_ids = {item["id"] for item in data.get("steps", [])}
        assert "warmup_nan_checks" in step_ids
        assert "overfitting_smells" in step_ids
        assert any("warmup" in warning for warning in data.get("warnings", []))
        assert any("overfit_smell" in warning for warning in data.get("warnings", []))
        review = data.get("review")
        assert review is not None
        for key in ["issues", "warnings", "suggestions", "next_tests"]:
            assert key in review
    finally:
        if plugin_dir.exists():
            shutil.rmtree(plugin_dir.parent.parent, ignore_errors=True)
