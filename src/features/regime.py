"""Deterministic market regime labels derived from feature inputs."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .build_features import FEATURE_COLUMNS

EMA_SPREAD_THRESHOLD = 0.001
RSI_BULL = 55.0
RSI_BEAR = 45.0
RSI_SLOPE_THRESHOLD = 0.1

ATR_PCT_LOW_QUANTILE = 0.33
ATR_PCT_HIGH_QUANTILE = 0.67

KMEANS_RANDOM_SEED = 7
KMEANS_CLUSTERS = 3

OUTPUT_PATH = Path("features/market_state.parquet")
PARQUET_COMPRESSION = "zstd"
PARQUET_COMPRESSION_LEVEL = 3
PARQUET_ROW_GROUP_SIZE = 100_000
PARQUET_DATA_PAGE_SIZE = 1_048_576
PARQUET_WRITE_STATISTICS = False

REGIME_COLUMNS = ["trend_state", "momentum_state", "volatility_regime"]


def _ensure_columns(df: pd.DataFrame, required: Iterable[str]) -> None:
    missing = sorted(set(required) - set(df.columns))
    if missing:
        raise ValueError(f"Missing required feature columns: {missing}")


def _volatility_cluster(
    atr_pct: pd.Series,
    *,
    n_clusters: int = KMEANS_CLUSTERS,
    seed: int = KMEANS_RANDOM_SEED,
) -> pd.Series | None:
    try:
        from sklearn.cluster import KMeans  # type: ignore
    except Exception:
        return None

    values = atr_pct.dropna().to_numpy().reshape(-1, 1)
    if values.shape[0] < n_clusters:
        return None

    kmeans = KMeans(n_clusters=n_clusters, random_state=seed, n_init=10)
    labels = kmeans.fit_predict(values)

    centers = kmeans.cluster_centers_.reshape(-1)
    order = np.argsort(centers)
    if n_clusters == 3:
        names = ("low", "mid", "high")
    else:
        names = tuple(f"cluster_{i}" for i in range(n_clusters))
    label_map = {int(order[i]): names[i] for i in range(n_clusters)}

    cluster = pd.Series(index=atr_pct.index, dtype="string")
    cluster.loc[atr_pct.dropna().index] = [label_map[int(label)] for label in labels]
    return cluster


def classify_regimes(
    features: pd.DataFrame,
    *,
    ema_spread_threshold: float = EMA_SPREAD_THRESHOLD,
    rsi_bull: float = RSI_BULL,
    rsi_bear: float = RSI_BEAR,
    rsi_slope_threshold: float = RSI_SLOPE_THRESHOLD,
    atr_pct_low_quantile: float = ATR_PCT_LOW_QUANTILE,
    atr_pct_high_quantile: float = ATR_PCT_HIGH_QUANTILE,
    include_volatility_cluster: bool = False,
) -> pd.DataFrame:
    """Classify deterministic regimes from precomputed features."""
    required = {"ema_20", "ema_50", "rsi_14", "rsi_slope_14_5", "atr_pct"}
    _ensure_columns(features, required)

    spread = features.get("ema_spread_20_50_pct")
    if spread is None:
        denom = features["ema_50"].replace(0.0, np.nan)
        spread = (features["ema_20"] - features["ema_50"]) / denom

    trend_state = pd.Series("flat", index=features.index, dtype="string")
    trend_state = trend_state.mask(spread > ema_spread_threshold, "up")
    trend_state = trend_state.mask(spread < -ema_spread_threshold, "down")

    rsi = features["rsi_14"].astype(float)
    rsi_slope_val = features["rsi_slope_14_5"].astype(float)

    momentum_state = pd.Series("neutral", index=features.index, dtype="string")
    bull_mask = (rsi >= rsi_bull) & (rsi_slope_val >= rsi_slope_threshold)
    bear_mask = (rsi <= rsi_bear) & (rsi_slope_val <= -rsi_slope_threshold)
    momentum_state = momentum_state.mask(bull_mask, "bull")
    momentum_state = momentum_state.mask(bear_mask, "bear")

    atr_pct = features["atr_pct"].astype(float)
    valid = atr_pct.dropna()
    volatility_regime = pd.Series("normal", index=features.index, dtype="string")

    if not valid.empty:
        low_cut = float(np.nanpercentile(valid, atr_pct_low_quantile * 100.0))
        high_cut = float(np.nanpercentile(valid, atr_pct_high_quantile * 100.0))
        if np.isfinite(low_cut) and np.isfinite(high_cut) and low_cut < high_cut:
            volatility_regime = volatility_regime.mask(atr_pct <= low_cut, "low")
            volatility_regime = volatility_regime.mask(atr_pct >= high_cut, "high")

    out = pd.DataFrame(
        {
            "trend_state": trend_state,
            "momentum_state": momentum_state,
            "volatility_regime": volatility_regime,
        },
        index=features.index,
    )

    if include_volatility_cluster:
        cluster = _volatility_cluster(atr_pct)
        if cluster is not None:
            out["volatility_cluster"] = cluster

    ordered = REGIME_COLUMNS + ([col for col in out.columns if col not in REGIME_COLUMNS])
    return out[ordered]


def build_market_state(
    features: pd.DataFrame,
    *,
    include_volatility_cluster: bool = False,
) -> pd.DataFrame:
    """Combine features with regime labels for storage or analysis."""
    regimes = classify_regimes(
        features,
        include_volatility_cluster=include_volatility_cluster,
    )
    combined = pd.concat([features, regimes], axis=1)
    ordered = FEATURE_COLUMNS + REGIME_COLUMNS
    if "volatility_cluster" in combined.columns:
        ordered.append("volatility_cluster")
    combined = combined[ordered]
    combined.index.name = features.index.name or "timestamp"
    return combined


def write_market_state(market_state: pd.DataFrame, out_path: Path = OUTPUT_PATH) -> Path:
    """Persist market state features with deterministic Parquet settings."""
    if market_state.empty:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        empty = market_state.copy()
        if empty.index.name is None:
            empty.index.name = "timestamp"
        frame = empty.reset_index()
    else:
        ordered = market_state.sort_index()
        ordered.index.name = ordered.index.name or "timestamp"
        frame = ordered.reset_index()

    table = pa.Table.from_pandas(frame, preserve_index=False)
    table = table.replace_schema_metadata(None)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        table,
        out_path,
        compression=PARQUET_COMPRESSION,
        compression_level=PARQUET_COMPRESSION_LEVEL,
        use_dictionary=False,
        row_group_size=PARQUET_ROW_GROUP_SIZE,
        data_page_size=PARQUET_DATA_PAGE_SIZE,
        write_statistics=PARQUET_WRITE_STATISTICS,
    )
    return out_path
