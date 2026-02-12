import json
import re
from datetime import datetime, timezone
from hashlib import sha256

from fastapi.testclient import TestClient

from apps.api.main import app


def _write_validation(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _hash_plugin_dir(path):
    hasher = sha256()
    for item in sorted(path.rglob("*")):
        if not item.is_file():
            continue
        rel = item.relative_to(path).as_posix()
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(item.read_bytes())
    return hasher.hexdigest()


def _index_hash(payload):
    canonical = json.dumps(
        {
            "total_plugins": payload.get("total_plugins"),
            "total_valid": payload.get("total_valid"),
            "total_invalid": payload.get("total_invalid"),
            "plugins": payload.get("plugins"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def _write_plugin_record(
    plugins_root,
    plugin_type,
    plugin_id,
    status,
    *,
    reason_codes=None,
    reason_messages=None,
    checked_at_utc="2026-02-01T00:00:00Z",
    source_hash="deadbeef",
    name="Demo",
    version="1.0.0",
    category="momentum",
):
    codes = list(reason_codes or [])
    messages = list(reason_messages or [""] * len(codes))
    payload = {
        "plugin_type": plugin_type,
        "id": plugin_id,
        "status": status,
        "reason_codes": codes,
        "reason_messages": messages,
        "checked_at_utc": checked_at_utc,
        "source_hash": source_hash,
        "name": name,
        "version": version,
        "category": category,
    }
    _write_validation(plugins_root / plugin_type / f"{plugin_id}.json", payload)
    return payload


def _write_index_payload(plugins_root, records, index_built_at="2026-02-01T00:00:00Z"):
    plugins = {}
    total_valid = 0
    total_invalid = 0
    for record in records:
        key = f"{record['plugin_type']}:{record['id']}"
        plugins[key] = {
            "id": record["id"],
            "plugin_type": record["plugin_type"],
            "status": record["status"],
            "source_hash": record.get("source_hash", ""),
            "checked_at_utc": record.get("checked_at_utc"),
            "name": record.get("name"),
            "version": record.get("version"),
            "category": record.get("category"),
        }
        if record["status"] == "VALID":
            total_valid += 1
        else:
            total_invalid += 1
    payload = {
        "index_built_at": index_built_at,
        "total_plugins": len(plugins),
        "total_valid": total_valid,
        "total_invalid": total_invalid,
        "plugins": plugins,
    }
    payload["content_hash"] = _index_hash(payload)
    _write_validation(plugins_root / "index.json", payload)
    return payload


def test_plugins_active_and_failed(monkeypatch, tmp_path):
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    plugins_root = artifacts_root / "plugin_validation"

    indicator_dir = tmp_path / "user_indicators" / "rsi"
    indicator_dir.mkdir(parents=True)
    (indicator_dir / "indicator.yaml").write_text(
        "id: rsi\nname: RSI\nversion: 1.0.0\ncategory: momentum\ninputs: [close]\n"
        "outputs: [rsi]\nparams: []\nwarmup_bars: 1\nnan_policy: propagate\n",
        encoding="utf-8",
    )
    (indicator_dir / "indicator.py").write_text(
        "def get_schema():\n    return {}\n\ndef compute(ctx):\n    return {'rsi': 0.0}\n",
        encoding="utf-8",
    )

    strategy_dir = tmp_path / "user_strategies" / "bad"
    strategy_dir.mkdir(parents=True)
    (strategy_dir / "strategy.yaml").write_text(
        "id: bad\nname: Bad\nversion: 1.0.0\ncategory: trend\nwarmup_bars: 1\n"
        "inputs:\n  series: [close]\n  indicators: []\n"
        "params: []\noutputs:\n  intents: [HOLD]\n  provides_confidence: false\n",
        encoding="utf-8",
    )
    (strategy_dir / "strategy.py").write_text(
        "def get_schema():\n    return {}\n\ndef on_bar(ctx):\n    return {'intent': 'HOLD'}\n",
        encoding="utf-8",
    )

    indicator_hash = _hash_plugin_dir(indicator_dir)
    strategy_hash = _hash_plugin_dir(strategy_dir)

    indicator_record = {
        "plugin_type": "indicator",
        "id": "rsi",
        "status": "VALID",
        "reason_codes": [],
        "reason_messages": [],
        "checked_at_utc": "2026-02-01T00:00:00Z",
        "source_hash": indicator_hash,
        "name": "RSI",
        "version": "1.0.0",
        "category": "momentum",
    }
    strategy_record = {
        "plugin_type": "strategy",
        "id": "bad",
        "status": "INVALID",
        "reason_codes": ["SCHEMA_MISSING_FIELD:id"],
        "reason_messages": ["Missing required field 'id'."],
        "checked_at_utc": "2026-02-01T00:00:00Z",
        "source_hash": strategy_hash,
        "name": "Bad",
        "version": "1.0.0",
        "category": "trend",
    }

    _write_validation(plugins_root / "indicator" / "rsi.json", indicator_record)
    _write_validation(plugins_root / "strategy" / "bad.json", strategy_record)

    index_payload = {
        "index_built_at": "2026-02-01T00:00:00Z",
        "total_plugins": 2,
        "total_valid": 1,
        "total_invalid": 1,
        "plugins": {
            "indicator:rsi": {
                "id": "rsi",
                "plugin_type": "indicator",
                "status": "VALID",
                "source_hash": indicator_hash,
                "checked_at_utc": "2026-02-01T00:00:00Z",
                "name": "RSI",
                "version": "1.0.0",
                "category": "momentum",
            },
            "strategy:bad": {
                "id": "bad",
                "plugin_type": "strategy",
                "status": "INVALID",
                "source_hash": strategy_hash,
                "checked_at_utc": "2026-02-01T00:00:00Z",
                "name": "Bad",
                "version": "1.0.0",
                "category": "trend",
            },
        },
    }
    index_payload["content_hash"] = _index_hash(index_payload)
    _write_validation(plugins_root / "index.json", index_payload)

    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    client = TestClient(app)

    active = client.get("/api/v1/plugins/active")
    assert active.status_code == 200
    active_payload = active.json()
    assert active_payload["indicators"][0]["id"] == "rsi"
    assert active_payload["indicators"][0]["name"] == "RSI"
    assert active_payload["indicators"][0]["version"] == "1.0.0"
    assert active_payload["indicators"][0]["category"] == "momentum"
    assert active_payload["strategies"] == []

    failed = client.get("/api/v1/plugins/failed")
    assert failed.status_code == 200
    failed_payload = failed.json()
    assert failed_payload["indicators"] == []
    assert failed_payload["strategies"][0]["id"] == "bad"
    assert failed_payload["strategies"][0]["errors"]


def test_plugins_missing_artifacts_returns_empty(monkeypatch, tmp_path):
    artifacts_root = tmp_path / "missing"
    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    client = TestClient(app)

    active = client.get("/api/v1/plugins/active")
    assert active.status_code == 200
    active_payload = active.json()
    assert active_payload == {"indicators": [], "strategies": []}

    failed = client.get("/api/v1/plugins/failed")
    assert failed.status_code == 200
    failed_payload = failed.json()
    assert failed_payload == {"indicators": [], "strategies": []}


def _write_indicator(tmp_path, plugin_id, yaml_content, py_content):
    indicator_dir = tmp_path / "user_indicators" / plugin_id
    indicator_dir.mkdir(parents=True, exist_ok=True)
    (indicator_dir / "indicator.yaml").write_text(yaml_content, encoding="utf-8")
    (indicator_dir / "indicator.py").write_text(py_content, encoding="utf-8")


def test_plugins_yaml_parse_error_fail_closed(monkeypatch, tmp_path):
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    plugins_root = artifacts_root / "plugin_validation"
    _write_plugin_record(
        plugins_root,
        "indicator",
        "bad_yaml",
        "INVALID",
        reason_codes=["YAML_PARSE_ERROR"],
        reason_messages=["Failed to parse indicator.yaml"],
    )

    client = TestClient(app)
    active = client.get("/api/v1/plugins/active")
    assert active.status_code == 200
    assert active.json() == {"indicators": [], "strategies": []}

    failed = client.get("/api/v1/plugins/failed")
    assert failed.status_code == 200
    payload = failed.json()
    assert payload["indicators"][0]["id"] == "bad_yaml"
    assert any(
        error["rule_id"] == "YAML_PARSE_ERROR" for error in payload["indicators"][0]["errors"]
    )


def test_plugins_ast_parse_error_fail_closed(monkeypatch, tmp_path):
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    plugins_root = artifacts_root / "plugin_validation"
    _write_plugin_record(
        plugins_root,
        "indicator",
        "bad_ast",
        "INVALID",
        reason_codes=["AST_PARSE_ERROR"],
        reason_messages=["indicator.py syntax error"],
    )

    client = TestClient(app)
    active = client.get("/api/v1/plugins/active")
    assert active.status_code == 200
    assert active.json() == {"indicators": [], "strategies": []}

    failed = client.get("/api/v1/plugins/failed")
    assert failed.status_code == 200
    payload = failed.json()
    assert payload["indicators"][0]["id"] == "bad_ast"
    assert any(
        error["rule_id"] == "AST_PARSE_ERROR" for error in payload["indicators"][0]["errors"]
    )


def test_plugins_validation_exception_fail_closed(monkeypatch, tmp_path):
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    plugins_root = artifacts_root / "plugin_validation"
    _write_plugin_record(
        plugins_root,
        "indicator",
        "boom_validator",
        "INVALID",
        reason_codes=["VALIDATION_EXCEPTION"],
        reason_messages=["Validator crashed: boom"],
    )

    client = TestClient(app)
    active = client.get("/api/v1/plugins/active")
    assert active.status_code == 200
    assert active.json() == {"indicators": [], "strategies": []}

    failed = client.get("/api/v1/plugins/failed")
    assert failed.status_code == 200
    payload = failed.json()
    assert payload["indicators"][0]["id"] == "boom_validator"
    assert any(
        error["rule_id"] == "VALIDATION_EXCEPTION" for error in payload["indicators"][0]["errors"]
    )


def test_plugins_validation_summary_healthy(monkeypatch, tmp_path):
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    plugins_root = artifacts_root / "plugin_validation"

    indicator_dir = tmp_path / "user_indicators" / "rsi"
    indicator_dir.mkdir(parents=True)
    (indicator_dir / "indicator.yaml").write_text(
        "id: rsi\nname: RSI\nversion: 1.0.0\ncategory: momentum\ninputs: [close]\n"
        "outputs: [value]\nparams: []\nwarmup_bars: 1\nnan_policy: propagate\n",
        encoding="utf-8",
    )
    (indicator_dir / "indicator.py").write_text(
        "def get_schema():\n    return {}\n\ndef compute(ctx):\n    return {'value': 1}\n",
        encoding="utf-8",
    )

    strategy_dir = tmp_path / "user_strategies" / "bad"
    strategy_dir.mkdir(parents=True)
    (strategy_dir / "strategy.yaml").write_text(
        "id: bad\nname: Bad\nversion: 1.0.0\ncategory: trend\nwarmup_bars: 1\n"
        "inputs:\n  series: [close]\n  indicators: []\n"
        "params: []\noutputs:\n  intents: [HOLD]\n  provides_confidence: false\n",
        encoding="utf-8",
    )
    (strategy_dir / "strategy.py").write_text(
        "def get_schema():\n    return {}\n\ndef on_bar(ctx):\n    return {'intent': 'HOLD'}\n",
        encoding="utf-8",
    )

    indicator_hash = _hash_plugin_dir(indicator_dir)
    strategy_hash = _hash_plugin_dir(strategy_dir)

    records = [
        _write_plugin_record(
            plugins_root,
            "indicator",
            "rsi",
            "VALID",
            source_hash=indicator_hash,
            name="RSI",
            category="momentum",
        ),
        _write_plugin_record(
            plugins_root,
            "strategy",
            "bad",
            "INVALID",
            reason_codes=["FORBIDDEN_IMPORT:os"],
            reason_messages=["Import 'os' is not allowed."],
            source_hash=strategy_hash,
            name="Bad",
            category="trend",
        ),
    ]
    index_payload = _write_index_payload(
        plugins_root, records, index_built_at="2026-02-01T00:00:00Z"
    )

    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    client = TestClient(app)

    summary_resp = client.get("/api/v1/plugins/validation-summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    for key in [
        "total",
        "valid",
        "invalid",
        "top_reason_codes",
        "index_built_at_utc",
        "index_content_hash",
    ]:
        assert key in summary
    assert summary["index_built_at_utc"] == "2026-02-01T00:00:00Z"
    assert summary["index_content_hash"] == index_payload["content_hash"]
    assert summary["top_reason_codes"][0] == {
        "code": "FORBIDDEN_IMPORT:os",
        "count": 1,
    }

    active_resp = client.get("/api/v1/plugins/active")
    failed_resp = client.get("/api/v1/plugins/failed")
    assert active_resp.status_code == 200
    assert failed_resp.status_code == 200
    active = active_resp.json()
    failed = failed_resp.json()
    valid_count = len(active["indicators"]) + len(active["strategies"])
    invalid_count = len(failed["indicators"]) + len(failed["strategies"])

    assert summary["total"] == valid_count + invalid_count
    assert summary["valid"] == valid_count
    assert summary["invalid"] == invalid_count


def test_plugins_validation_summary_rebuild_from_artifacts(monkeypatch, tmp_path):
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    plugins_root = artifacts_root / "plugin_validation"

    _write_plugin_record(plugins_root, "indicator", "rsi", "VALID")
    _write_plugin_record(
        plugins_root,
        "strategy",
        "bad",
        "INVALID",
        reason_codes=["FORBIDDEN_IMPORT:os"],
        reason_messages=["Import 'os' is not allowed."],
    )
    (plugins_root / "index.json").parent.mkdir(parents=True, exist_ok=True)
    (plugins_root / "index.json").write_text("{invalid", encoding="utf-8")

    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    client = TestClient(app)

    summary_resp = client.get("/api/v1/plugins/validation-summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert "error" not in summary
    assert summary["total"] == 2
    assert summary["valid"] == 1
    assert summary["invalid"] == 1
    assert summary["index_content_hash"]
    assert summary["top_reason_codes"][0]["code"] == "FORBIDDEN_IMPORT:os"
    assert summary["top_reason_codes"][0]["count"] == 1
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", summary["index_built_at_utc"])


def test_plugins_validation_summary_rebuild_failure_fail_closed(monkeypatch, tmp_path):
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    plugins_root = artifacts_root / "plugin_validation"

    _write_plugin_record(plugins_root, "indicator", "rsi", "VALID")
    _write_plugin_record(
        plugins_root,
        "strategy",
        "bad",
        "INVALID",
        reason_codes=["FORBIDDEN_IMPORT:os"],
        reason_messages=["Import 'os' is not allowed."],
    )
    (plugins_root / "index.json").parent.mkdir(parents=True, exist_ok=True)
    (plugins_root / "index.json").write_text("{invalid", encoding="utf-8")

    def boom(_root):
        raise RuntimeError("boom")

    monkeypatch.setattr("src.plugins.registry._rebuild_index_from_artifacts", boom)

    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    client = TestClient(app)

    summary_resp = client.get("/api/v1/plugins/validation-summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert "error" in summary
    assert summary["total"] == 2
    assert summary["valid"] == 0
    assert summary["invalid"] == 2
    assert summary["index_content_hash"] == ""
    assert summary["index_built_at_utc"] is None
    assert summary["top_reason_codes"] == []

    active_resp = client.get("/api/v1/plugins/active")
    assert active_resp.status_code == 200
    assert active_resp.json() == {"indicators": [], "strategies": []}

    failed_resp = client.get("/api/v1/plugins/failed")
    assert failed_resp.status_code == 200
    failed_payload = failed_resp.json()
    assert failed_payload["indicators"] == []
    assert failed_payload["strategies"][0]["id"] == "bad"


def test_plugins_validation_summary_lock_contention(monkeypatch, tmp_path):
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    plugins_root = artifacts_root / "plugin_validation"

    _write_plugin_record(plugins_root, "indicator", "rsi", "VALID")
    _write_plugin_record(
        plugins_root,
        "strategy",
        "bad",
        "INVALID",
        reason_codes=["FORBIDDEN_IMPORT:os"],
        reason_messages=["Import 'os' is not allowed."],
    )
    (plugins_root / "index.json").parent.mkdir(parents=True, exist_ok=True)
    (plugins_root / "index.json").write_text("{invalid", encoding="utf-8")

    lock_payload = {
        "pid": 123,
        "created_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    lock_path = plugins_root / ".index.lock"
    lock_path.write_text(json.dumps(lock_payload), encoding="utf-8")

    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    client = TestClient(app)

    summary_resp = client.get("/api/v1/plugins/validation-summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["error"] == "index rebuild locked"
    assert summary["total"] == 2
    assert summary["valid"] == 0
    assert summary["invalid"] == 2
    assert summary["index_content_hash"] == ""
    assert summary["index_built_at_utc"] is None
    assert summary["top_reason_codes"] == []


def test_plugins_validation_summary_lock_invalid_json_blocks(monkeypatch, tmp_path):
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    plugins_root = artifacts_root / "plugin_validation"

    _write_plugin_record(plugins_root, "indicator", "rsi", "VALID")
    _write_plugin_record(
        plugins_root,
        "strategy",
        "bad",
        "INVALID",
        reason_codes=["FORBIDDEN_IMPORT:os"],
        reason_messages=["Import 'os' is not allowed."],
    )
    (plugins_root / "index.json").parent.mkdir(parents=True, exist_ok=True)
    (plugins_root / "index.json").write_text("{invalid", encoding="utf-8")

    lock_path = plugins_root / ".index.lock"
    lock_path.write_text("{invalid", encoding="utf-8")

    monkeypatch.setenv("ARTIFACTS_ROOT", str(artifacts_root))
    client = TestClient(app)

    summary_resp = client.get("/api/v1/plugins/validation-summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["error"] == "index rebuild locked"
    assert summary["total"] == 2
    assert summary["valid"] == 0
    assert summary["invalid"] == 2
    assert summary["index_content_hash"] == ""
    assert summary["index_built_at_utc"] is None
    assert summary["top_reason_codes"] == []

    active_resp = client.get("/api/v1/plugins/active")
    assert active_resp.status_code == 200
    assert active_resp.json() == {"indicators": [], "strategies": []}
