from __future__ import annotations

from pathlib import Path

import pandas as pd

from chatbot import Chatbot, ChatbotConfig


def _write_artifacts(base_dir: Path) -> dict[str, Path]:
    workspaces = base_dir / "workspaces" / "run1"
    reports = base_dir / "reports"
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

    return {
        "trades": trades_path,
        "selector": selector_path,
        "risk": risk_path,
    }


def _snapshot_files(root_dir: Path) -> set[str]:
    return {path.relative_to(root_dir).as_posix() for path in root_dir.rglob("*") if path.is_file()}


def test_chatbot_read_only(tmp_path: Path) -> None:
    paths = _write_artifacts(tmp_path)
    config = ChatbotConfig(
        root_dir=tmp_path,
        trades_path=paths["trades"],
        selector_trace_path=paths["selector"],
        risk_timeline_path=paths["risk"],
    )

    before = _snapshot_files(tmp_path)
    response = Chatbot(config).respond("daily summary")
    after = _snapshot_files(tmp_path)

    assert before == after
    assert "trades.parquet" in response
    assert "selector_trace.json" in response
    assert "risk_timeline.json" in response
