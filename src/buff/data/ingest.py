"""OHLCV ingestion from Binance Futures via ccxt."""

import time
from dataclasses import dataclass

import ccxt
import pandas as pd


@dataclass
class IngestConfig:
    """Configuration for OHLCV ingestion."""

    exchange: str = "binance"
    market_type: str = "future"
    timeframe: str = "1h"
    limit: int = 1000  # Binance max: 1000 candles per request
    rate_limit: bool = True


def make_exchange(cfg: IngestConfig) -> ccxt.Exchange:
    """Create and configure ccxt exchange instance.

    Args:
        cfg: IngestConfig with exchange, market_type, rate_limit settings.

    Returns:
        Configured ccxt.Exchange instance.
    """
    params = {"defaultType": cfg.market_type}
    if not cfg.rate_limit:
        params["enableRateLimit"] = False

    exchange_class = getattr(ccxt, cfg.exchange)
    return exchange_class(params)


def fetch_ohlcv_all(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    since_ms: int,
    limit: int,
) -> pd.DataFrame:
    """Fetch all OHLCV candles since since_ms, deduplicate, sort, and return DataFrame.

    Implements pagination with retry logic to fetch complete historical data.

    Args:
        exchange: ccxt exchange instance.
        symbol: Trading pair symbol (e.g., "BTC/USDT").
        timeframe: Timeframe (e.g., "1h").
        since_ms: Timestamp in milliseconds to start fetching from.
        limit: Max candles per fetch request.

    Returns:
        DataFrame with columns: ts, open, high, low, close, volume
        Indexed by ts (UTC, ascending order). No duplicates.
    """
    all_ohlcv = []
    current_since = since_ms
    prev_last_ts = None
    max_retries = 3
    retry_delays = [1.0, 2.0, 4.0]

    while True:
        ohlcv = None
        last_error = None

        # Retry logic with exponential backoff
        for attempt in range(max_retries):
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=current_since, limit=limit)
                break  # Success
            except (ccxt.NetworkError, ccxt.ExchangeError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = retry_delays[attempt]
                    time.sleep(delay)
                continue

        # If all retries failed, raise the last error
        if ohlcv is None:
            if last_error:
                raise last_error
            break

        # If batch is empty, we've reached the end
        if not ohlcv:
            break

        all_ohlcv.extend(ohlcv)

        # CCXT returns [timestamp_ms, o, h, l, c, volume]
        last_timestamp = ohlcv[-1][0]

        # Check for progress: if last_ts didn't advance, stop
        if prev_last_ts is not None and last_timestamp <= prev_last_ts:
            break

        prev_last_ts = last_timestamp

        # Stop if fetch returned fewer than limit candles (likely at the end)
        if len(ohlcv) < limit:
            break

        # Move to next batch (avoid overlap by starting at last_ts + 1)
        current_since = last_timestamp + 1

    if not all_ohlcv:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])

    # Convert to DataFrame
    df = pd.DataFrame(all_ohlcv, columns=["ts_ms", "open", "high", "low", "close", "volume"])

    # Convert timestamp from ms to UTC datetime
    df["ts"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
    df = df.drop("ts_ms", axis=1)

    # Deduplicate by ts, keeping first occurrence
    df = df.drop_duplicates(subset=["ts"], keep="first")

    # Sort ascending by ts
    df = df.sort_values("ts").reset_index(drop=True)

    return df
