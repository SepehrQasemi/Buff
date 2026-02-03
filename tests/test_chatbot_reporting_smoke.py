from __future__ import annotations

from pathlib import Path

import pandas as pd

from chatbot import Chatbot, ChatbotConfig


def test_chatbot_reporting_smoke(tmp_path: Path) -> None:
    workspaces = tmp_path / "workspaces" / "run1"
    reports = tmp_path / "reports"
    workspaces.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    trades = pd.DataFrame(
        [
            {
                "run_id": "run1",
                "ts_utc": "2026-02-02T00:00:00Z",
                "order_id": "1",
                "symbol": "BTC",
                "side": "BUY",
                "qty": 1.5,
                "status": "EXECUTED",
                "reason": "",
                "execution_status": "FILLED",
            },
            {
                "run_id": "run1",
                "ts_utc": "2026-02-02T00:01:00Z",
                "order_id": "2",
                "symbol": "BTC",
                "side": "SELL",
                "qty": 0.5,
                "status": "BLOCKED",
                "reason": "risk",
                "execution_status": "SKIPPED",
            },
            {
                "run_id": "run1",
                "ts_utc": "2026-02-02T00:02:00Z",
                "order_id": "3",
                "symbol": "ETH",
                "side": "BUY",
                "qty": 2.0,
                "status": "EXECUTED",
                "reason": "",
                "execution_status": "FILLED",
            },
        ]
    )
    trades_path = workspaces / "trades.parquet"
    trades.to_parquet(trades_path, index=False)

    selector_path = workspaces / "selector_trace.json"
    selector_path.write_text(
        "[\n"
        '  {"ts_utc": "2026-02-02T00:00:30Z", "strategy_id": "TREND", "status": "selected"},\n'
        '  {"ts_utc": "2026-02-02T00:01:30Z", "strategy_id": "MEAN", "status": "rejected"}\n'
        "]\n",
        encoding="utf-8",
    )

    risk_path = reports / "risk_timeline.json"
    risk_path.write_text(
        "[\n"
        '  {"ts_utc": "2026-02-02T00:00:00+00:00", "risk_state": "green"},\n'
        '  {"ts_utc": "2026-02-02T01:00:00+00:00", "risk_state": "red"}\n'
        "]\n",
        encoding="utf-8",
    )

    config = ChatbotConfig(
        root_dir=tmp_path,
        trades_path=trades_path,
        selector_trace_path=selector_path,
        risk_timeline_path=risk_path,
    )

    response = Chatbot(config).respond("daily summary")

    assert "# Daily Summary" in response
    assert "total: 3" in response
    assert "symbols: BTC=2, ETH=1" in response
    assert "sides: BUY=2, SELL=1" in response
    assert "status: BLOCKED=1, EXECUTED=2" in response
    assert "qty_total: 4.0000" in response
    assert "strategy_id: MEAN=1, TREND=1" in response
    assert "status: rejected=1, selected=1" in response
    assert "risk_state: green=1, red=1" in response
    assert "latest: red @ 2026-02-02T01:00:00+00:00" in response
    assert "workspaces/run1/trades.parquet" in response
    assert "workspaces/run1/selector_trace.json" in response
    assert "reports/risk_timeline.json" in response
