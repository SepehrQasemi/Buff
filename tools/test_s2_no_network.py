from __future__ import annotations

from pathlib import Path
import socket
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from s2.core import NetworkDisabledError, S2CoreConfig, run_s2_core_loop
from s2.models import FeeModel, FundingModel, SlippageBucket, SlippageModel


def test_s2_no_network_blocks_egress() -> None:
    config = S2CoreConfig(
        fee_model=FeeModel(maker_bps=0.0, taker_bps=0.0),
        slippage_model=SlippageModel(buckets=(SlippageBucket(max_notional_quote=None, bps=0.0),)),
        funding_model=FundingModel(interval_minutes=0),
    )
    bars = [
        {
            "ts_utc": "2026-02-01T00:00:00Z",
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "volume": 1.0,
        }
    ]

    def _strategy(event, state, rng):
        del event, state, rng
        socket.getaddrinfo("example.com", 443)
        return "HOLD"

    with pytest.raises(NetworkDisabledError):
        run_s2_core_loop(bars=bars, config=config, strategy_fn=_strategy)
