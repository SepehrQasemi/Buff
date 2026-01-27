"""Generate golden indicator outputs for RSI/EMA/ATR using ta library."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

try:
    from ta.momentum import RSIIndicator
    from ta.trend import EMAIndicator
    from ta.volatility import AverageTrueRange
except ImportError as exc:
    raise SystemExit("ta library is required. Install with: pip install ta") from exc


def _make_ohlcv(rows: int = 200) -> pd.DataFrame:
    rng = np.random.RandomState(42)
    ts = pd.date_range("2023-01-01", periods=rows, freq="1h", tz="UTC")
    base = 100 + rng.normal(0, 0.5, size=rows).cumsum()
    open_ = base
    close = base + rng.normal(0, 0.3, size=rows)
    span = np.abs(rng.normal(0.2, 0.1, size=rows))
    high = np.maximum(open_, close) + span
    low = np.minimum(open_, close) - span
    volume = np.abs(rng.normal(1000, 50, size=rows))

    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def main() -> None:
    df = _make_ohlcv()

    rsi = RSIIndicator(close=df["close"], window=14, fillna=False).rsi()
    ema = EMAIndicator(close=df["close"], window=20, fillna=False).ema_indicator()
    atr = AverageTrueRange(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=14,
        fillna=False,
    ).average_true_range()

    out = df[["timestamp", "open", "high", "low", "close"]].copy()
    out["rsi_14"] = rsi
    out["ema_20"] = ema
    out["atr_14"] = atr

    out_dir = Path("tests/goldens")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "expected.csv"
    out.to_csv(out_path, index=False)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
