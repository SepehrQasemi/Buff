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

from buff.features.indicators import bollinger_bands, macd, rolling_std, sma


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
    sma_20 = sma(df["close"], period=20)
    std_20 = rolling_std(df["close"], period=20, ddof=0)
    bb = bollinger_bands(df["close"], period=20, k=2.0, ddof=0)
    macd_df = macd(df["close"], fast=12, slow=26, signal=9)

    out = df[["timestamp", "open", "high", "low", "close"]].copy()
    out["rsi_14"] = rsi
    out["ema_20"] = ema
    out["atr_14"] = atr
    out["sma_20"] = sma_20
    out["std_20"] = std_20
    out["bb_mid_20_2"] = bb["mid"]
    out["bb_upper_20_2"] = bb["upper"]
    out["bb_lower_20_2"] = bb["lower"]
    out["macd_12_26_9"] = macd_df["macd"]
    out["macd_signal_12_26_9"] = macd_df["signal"]
    out["macd_hist_12_26_9"] = macd_df["hist"]

    out_dir = Path("tests/goldens")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "expected.csv"
    out.to_csv(out_path, index=False)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
