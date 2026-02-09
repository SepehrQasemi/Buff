from fastapi.testclient import TestClient
import yaml

from apps.api.main import app


def _file_map(files):
    return {item["path"]: item["contents"] for item in files}


def test_chat_modes():
    client = TestClient(app)
    response = client.get("/api/v1/chat/modes")
    assert response.status_code == 200
    payload = response.json()
    modes = {item["mode"] for item in payload.get("modes", [])}
    assert "add_indicator" in modes
    assert "add_strategy" in modes
    assert "review_plugin" in modes
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
