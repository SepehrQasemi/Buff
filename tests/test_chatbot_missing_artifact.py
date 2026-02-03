from __future__ import annotations

from pathlib import Path

from chatbot import Chatbot, ChatbotConfig


def test_chatbot_missing_artifact(tmp_path: Path) -> None:
    workspaces = tmp_path / "workspaces" / "run1"
    reports = tmp_path / "reports"
    reports.mkdir(parents=True)

    risk_path = reports / "risk_timeline.json"
    risk_path.write_text("[]\n", encoding="utf-8")

    trades_path = workspaces / "trades.parquet"
    selector_path = workspaces / "selector_trace.json"

    config = ChatbotConfig(
        root_dir=tmp_path,
        trades_path=trades_path,
        selector_trace_path=selector_path,
        risk_timeline_path=risk_path,
    )

    response = Chatbot(config).respond("daily summary")

    assert response.startswith("unknown")
    assert "workspaces/run1/trades.parquet" in response
    assert "workspaces/run1/selector_trace.json" in response
    assert "reports/risk_timeline.json" in response
