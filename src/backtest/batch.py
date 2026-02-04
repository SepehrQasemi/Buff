from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import re
from typing import Any

import pandas as pd

from backtest.harness import run_backtest


REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class BatchResult:
    batch_id: str
    batch_dir: Path
    summary_csv_path: Path
    summary_json_path: Path
    index_json_path: Path
    summary: pd.DataFrame
    index: dict[str, dict[str, object]]


def _iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    value = dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _canonical_json(payload) + "\n",
        encoding="utf-8",
    )
    return path


def _slugify(value: str) -> str:
    value = value.strip()
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_") or "dataset"


def _data_quality(df: object) -> tuple[dict[str, object], str | None]:
    details: dict[str, object] = {
        "missing_required_columns": [],
        "nan_counts": {},
        "non_monotonic_timestamps": False,
        "duplicate_timestamps": False,
        "num_rows": 0,
    }
    if not isinstance(df, pd.DataFrame):
        return details, "dataset_not_dataframe"

    details["num_rows"] = int(len(df))
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    details["missing_required_columns"] = missing
    if missing:
        return details, f"missing_required_columns:{','.join(missing)}"

    if not isinstance(df.index, pd.DatetimeIndex):
        return details, "index_not_datetime"
    if df.index.tz is None:
        return details, "index_not_utc"

    duplicated = df.index.duplicated().any()
    details["duplicate_timestamps"] = bool(duplicated)
    if duplicated:
        return details, "duplicate_timestamps"

    if not df.index.is_monotonic_increasing:
        details["non_monotonic_timestamps"] = True

    nan_counts: dict[str, int] = {}
    for col in REQUIRED_COLUMNS:
        series = pd.to_numeric(df[col], errors="coerce")
        nan_counts[col] = int(series.isna().sum())
    details["nan_counts"] = nan_counts
    if any(count > 0 for count in nan_counts.values()):
        return details, "nan_values_present"

    if len(df) < 2:
        return details, "insufficient_bars"

    return details, None


def _config_id(config: object) -> tuple[str, str]:
    payload = _canonical_json(config)
    digest = sha256(payload.encode("utf-8")).hexdigest()[:8]
    return digest, payload


def _expand_param_grid(param_grid: dict[str, list[Any]] | None) -> list[dict[str, Any]]:
    if not param_grid:
        return [{}]
    keys = sorted(param_grid)
    values = [list(param_grid[key]) for key in keys]
    out: list[dict[str, Any]] = []
    for combo in product(*values):
        out.append({key: value for key, value in zip(keys, combo, strict=True)})
    return out


def _strategy_usage(decision_records_path: Path) -> tuple[dict[str, int], str | None, float, int]:
    counts: dict[str, int] = {}
    total = 0
    for line in decision_records_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        selection = payload.get("selection", {})
        if not isinstance(selection, dict):
            selection = {}
        strategy_id = selection.get("strategy_id")
        strategy_id = str(strategy_id) if strategy_id else "NONE"
        counts[strategy_id] = counts.get(strategy_id, 0) + 1
        total += 1

    if total == 0:
        return {}, None, 0.0, 0

    primary_strategy, primary_count = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    primary_share = float(primary_count) / float(total)
    return counts, primary_strategy, primary_share, total


def _pair_id(
    dataset_key: str, timeframe: str, config_id: str, window_index: int | None = None
) -> str:
    window_part = "" if window_index is None else str(int(window_index))
    pair_id_source = f"{dataset_key}|{timeframe}|{config_id}|{window_part}"
    return sha256(pair_id_source.encode("utf-8")).hexdigest()[:10]


def run_batch_backtests(
    datasets: dict[str, pd.DataFrame],
    *,
    out_dir: Path,
    timeframe: str,
    start_at_utc: datetime | None,
    end_at_utc: datetime | None,
    initial_equity: float,
    costs: dict[str, object] | None = None,
    seed_run_id_prefix: str | None = None,
    param_grid: dict[str, list[Any]] | None = None,
    split: dict[str, object] | None = None,
) -> BatchResult:
    commission_bps = 0.0
    slippage_bps = 0.0
    if costs is not None:
        commission_bps = float(costs.get("commission_bps", 0.0))
        slippage_bps = float(costs.get("slippage_bps", 0.0))
        if commission_bps < 0.0 or slippage_bps < 0.0:
            raise ValueError("batch_invalid_costs")

    split_type = ""
    split_cfg: dict[str, object] | None = None
    if split is not None:
        if not isinstance(split, dict):
            raise ValueError("batch_invalid_split")
        split_type_value = split.get("type")
        if split_type_value not in {"holdout", "walk_forward"}:
            raise ValueError("batch_invalid_split")
        split_type = str(split_type_value)
        split_cfg = dict(split)
        if split_type == "holdout":
            train_frac = split.get("train_frac")
            if (
                not isinstance(train_frac, (int, float))
                or isinstance(train_frac, bool)
                or not (0.0 < float(train_frac) < 1.0)
            ):
                raise ValueError("batch_invalid_split")
            for key in ("min_train_bars", "min_test_bars"):
                value = split.get(key)
                if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                    raise ValueError("batch_invalid_split")
        else:
            for key in ("train_bars", "test_bars", "step_bars"):
                value = split.get(key)
                if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                    raise ValueError("batch_invalid_split")

    batch_id = _slugify(seed_run_id_prefix) if seed_run_id_prefix else _now_id()
    batch_dir = Path(out_dir) / f"batch_{batch_id}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    base_start_iso = _iso_utc(start_at_utc) if start_at_utc is not None else None
    base_end_iso = _iso_utc(end_at_utc) if end_at_utc is not None else None

    rows: list[dict[str, object]] = []
    index_payload: dict[str, dict[str, object]] = {}
    used_run_ids: set[str] = set()
    overall_strategy_counts: dict[str, int] = {}
    overall_decisions = 0

    ordered = sorted(
        ((symbol, timeframe, df) for symbol, df in datasets.items()), key=lambda x: (x[0], x[1])
    )
    configs = _expand_param_grid(param_grid)
    for symbol, tf, df in ordered:
        symbol_str = str(symbol)
        quality, error = _data_quality(df)
        timestamp_repaired = False
        timestamp_repaired_reason = None
        if (
            error is None
            and quality.get("non_monotonic_timestamps")
            and isinstance(df, pd.DataFrame)
        ):
            df = df.sort_index()
            timestamp_repaired = True
            timestamp_repaired_reason = "non_monotonic_sorted"

        if error is not None:
            for config in configs:
                effective_start = config.get("start_at_utc", start_at_utc)
                effective_end = config.get("end_at_utc", end_at_utc)
                if effective_start is not None and not isinstance(effective_start, datetime):
                    raise ValueError("batch_invalid_start_at_utc")
                if effective_end is not None and not isinstance(effective_end, datetime):
                    raise ValueError("batch_invalid_end_at_utc")
                start_iso = _iso_utc(effective_start) if effective_start is not None else None
                end_iso = _iso_utc(effective_end) if effective_end is not None else None

                config_obj = {
                    "timeframe": tf,
                    "start_at_utc": start_iso,
                    "end_at_utc": end_iso,
                    "params": dict(config),
                }
                config_id, config_json = _config_id(config_obj)
                run_id_prefix = f"{batch_id}_{_slugify(symbol_str)}_{_slugify(tf)}"
                run_id_base = (
                    f"{run_id_prefix}_{config_id}" if param_grid is not None else run_id_prefix
                )
                run_id = run_id_base
                suffix = 2
                while run_id in used_run_ids:
                    run_id = f"{run_id_base}_{suffix}"
                    suffix += 1
                used_run_ids.add(run_id)
                row = {
                    "symbol": symbol_str,
                    "timeframe": tf,
                    "split_type": split_type,
                    "segment": "",
                    "pair_id": "",
                    "window_index": None,
                    "status": "FAILED",
                    "run_id": run_id,
                    "config_id": config_id,
                    "config_json": config_json,
                    "error": error,
                    "data_quality": quality,
                    "timestamp_repaired": timestamp_repaired,
                    "timestamp_repaired_reason": timestamp_repaired_reason,
                    "strategy_share_available": False,
                    "strategy_share_error": "",
                    "strategy_counts_json": "{}",
                    "primary_strategy": "",
                    "primary_strategy_share": 0.0,
                    "initial_equity": float(initial_equity),
                    "commission_bps": float(commission_bps),
                    "slippage_bps": float(slippage_bps),
                    "start_at_utc": start_iso,
                    "end_at_utc": end_iso,
                }
                rows.append(row)
                index_payload[run_id] = {
                    "status": "FAILED",
                    "symbol": symbol_str,
                    "timeframe": tf,
                    "split_type": split_type,
                    "segment": "",
                    "pair_id": "",
                    "window_index": None,
                    "config_id": config_id,
                    "config_json": config_json,
                    "error": error,
                    "artifacts": {},
                }
            continue

        for config in configs:
            effective_initial_equity = float(config.get("initial_equity", initial_equity))
            effective_commission_bps = float(config.get("commission_bps", commission_bps))
            effective_slippage_bps = float(config.get("slippage_bps", slippage_bps))
            effective_start = config.get("start_at_utc", start_at_utc)
            effective_end = config.get("end_at_utc", end_at_utc)
            if effective_commission_bps < 0.0 or effective_slippage_bps < 0.0:
                raise ValueError("batch_invalid_costs")
            if effective_start is not None and not isinstance(effective_start, datetime):
                raise ValueError("batch_invalid_start_at_utc")
            if effective_end is not None and not isinstance(effective_end, datetime):
                raise ValueError("batch_invalid_end_at_utc")

            start_iso = _iso_utc(effective_start) if effective_start is not None else None
            end_iso = _iso_utc(effective_end) if effective_end is not None else None

            config_obj = {
                "timeframe": tf,
                "start_at_utc": start_iso,
                "end_at_utc": end_iso,
                "initial_equity": effective_initial_equity,
                "costs": {
                    "commission_bps": effective_commission_bps,
                    "slippage_bps": effective_slippage_bps,
                },
                "params": dict(config),
            }
            config_id, config_json = _config_id(config_obj)

            run_id_prefix = f"{batch_id}_{_slugify(symbol_str)}_{_slugify(tf)}"
            run_id_base = (
                f"{run_id_prefix}_{config_id}" if param_grid is not None else run_id_prefix
            )
            if split_type:
                df_for_split = df
                if effective_start is not None:
                    df_for_split = df_for_split.loc[
                        df_for_split.index >= pd.to_datetime(effective_start, utc=True)
                    ]
                if effective_end is not None:
                    df_for_split = df_for_split.loc[
                        df_for_split.index <= pd.to_datetime(effective_end, utc=True)
                    ]

                split_runs: list[dict[str, object]] = []
                if split_type == "holdout":
                    train_frac = float(split_cfg["train_frac"]) if split_cfg is not None else 0.0
                    min_train_bars = (
                        int(split_cfg["min_train_bars"]) if split_cfg is not None else 0
                    )
                    min_test_bars = int(split_cfg["min_test_bars"]) if split_cfg is not None else 0
                    train_bars = int(len(df_for_split) * train_frac)
                    test_bars = len(df_for_split) - train_bars
                    pair_id = _pair_id(symbol_str, tf, config_id)
                    if train_bars < min_train_bars or test_bars < min_test_bars:
                        row = {
                            "symbol": symbol_str,
                            "timeframe": tf,
                            "split_type": split_type,
                            "segment": "",
                            "pair_id": pair_id,
                            "window_index": None,
                            "status": "FAILED",
                            "run_id": run_id_base,
                            "config_id": config_id,
                            "config_json": config_json,
                            "error": "insufficient_bars_for_split",
                            "data_quality": quality,
                            "timestamp_repaired": timestamp_repaired,
                            "timestamp_repaired_reason": timestamp_repaired_reason,
                            "strategy_share_available": False,
                            "strategy_share_error": "",
                            "strategy_counts_json": "{}",
                            "primary_strategy": "",
                            "primary_strategy_share": 0.0,
                            "initial_equity": float(effective_initial_equity),
                            "commission_bps": float(effective_commission_bps),
                            "slippage_bps": float(effective_slippage_bps),
                            "start_at_utc": start_iso,
                            "end_at_utc": end_iso,
                        }
                        rows.append(row)
                        index_payload[run_id_base] = {
                            "status": "FAILED",
                            "symbol": symbol_str,
                            "timeframe": tf,
                            "split_type": split_type,
                            "segment": "",
                            "pair_id": pair_id,
                            "window_index": None,
                            "config_id": config_id,
                            "config_json": config_json,
                            "error": "insufficient_bars_for_split",
                            "artifacts": {},
                        }
                        continue
                    split_runs = [
                        {
                            "run_id": f"{run_id_base}__seg-TRAIN",
                            "segment": "TRAIN",
                            "pair_id": pair_id,
                            "window_index": None,
                            "df": df_for_split.iloc[:train_bars],
                        },
                        {
                            "run_id": f"{run_id_base}__seg-TEST",
                            "segment": "TEST",
                            "pair_id": pair_id,
                            "window_index": None,
                            "df": df_for_split.iloc[train_bars:],
                        },
                    ]
                else:
                    train_bars = int(split_cfg["train_bars"]) if split_cfg is not None else 0
                    test_bars = int(split_cfg["test_bars"]) if split_cfg is not None else 0
                    step_bars = int(split_cfg["step_bars"]) if split_cfg is not None else 0
                    if len(df_for_split) < (train_bars + test_bars):
                        pair_id = _pair_id(symbol_str, tf, config_id, 0)
                        row = {
                            "symbol": symbol_str,
                            "timeframe": tf,
                            "split_type": split_type,
                            "segment": "",
                            "pair_id": pair_id,
                            "window_index": None,
                            "status": "FAILED",
                            "run_id": run_id_base,
                            "config_id": config_id,
                            "config_json": config_json,
                            "error": "insufficient_bars_for_split",
                            "data_quality": quality,
                            "timestamp_repaired": timestamp_repaired,
                            "timestamp_repaired_reason": timestamp_repaired_reason,
                            "strategy_share_available": False,
                            "strategy_share_error": "",
                            "strategy_counts_json": "{}",
                            "primary_strategy": "",
                            "primary_strategy_share": 0.0,
                            "initial_equity": float(effective_initial_equity),
                            "commission_bps": float(effective_commission_bps),
                            "slippage_bps": float(effective_slippage_bps),
                            "start_at_utc": start_iso,
                            "end_at_utc": end_iso,
                        }
                        rows.append(row)
                        index_payload[run_id_base] = {
                            "status": "FAILED",
                            "symbol": symbol_str,
                            "timeframe": tf,
                            "split_type": split_type,
                            "segment": "",
                            "pair_id": pair_id,
                            "window_index": None,
                            "config_id": config_id,
                            "config_json": config_json,
                            "error": "insufficient_bars_for_split",
                            "artifacts": {},
                        }
                        continue
                    k = 0
                    start_idx = 0
                    while True:
                        train_end = start_idx + train_bars
                        test_end = train_end + test_bars
                        if test_end > len(df_for_split):
                            break
                        pair_id = _pair_id(symbol_str, tf, config_id, k)
                        split_runs.append(
                            {
                                "run_id": f"{run_id_base}__wf-{k}__seg-TRAIN",
                                "segment": "TRAIN",
                                "pair_id": pair_id,
                                "window_index": k,
                                "df": df_for_split.iloc[start_idx:train_end],
                            }
                        )
                        split_runs.append(
                            {
                                "run_id": f"{run_id_base}__wf-{k}__seg-TEST",
                                "segment": "TEST",
                                "pair_id": pair_id,
                                "window_index": k,
                                "df": df_for_split.iloc[train_end:test_end],
                            }
                        )
                        k += 1
                        start_idx += step_bars
                    if not split_runs:
                        pair_id = _pair_id(symbol_str, tf, config_id, 0)
                        row = {
                            "symbol": symbol_str,
                            "timeframe": tf,
                            "split_type": split_type,
                            "segment": "",
                            "pair_id": pair_id,
                            "window_index": None,
                            "status": "FAILED",
                            "run_id": run_id_base,
                            "config_id": config_id,
                            "config_json": config_json,
                            "error": "insufficient_bars_for_split",
                            "data_quality": quality,
                            "timestamp_repaired": timestamp_repaired,
                            "timestamp_repaired_reason": timestamp_repaired_reason,
                            "strategy_share_available": False,
                            "strategy_share_error": "",
                            "strategy_counts_json": "{}",
                            "primary_strategy": "",
                            "primary_strategy_share": 0.0,
                            "initial_equity": float(effective_initial_equity),
                            "commission_bps": float(effective_commission_bps),
                            "slippage_bps": float(effective_slippage_bps),
                            "start_at_utc": start_iso,
                            "end_at_utc": end_iso,
                        }
                        rows.append(row)
                        index_payload[run_id_base] = {
                            "status": "FAILED",
                            "symbol": symbol_str,
                            "timeframe": tf,
                            "split_type": split_type,
                            "segment": "",
                            "pair_id": pair_id,
                            "window_index": None,
                            "config_id": config_id,
                            "config_json": config_json,
                            "error": "insufficient_bars_for_split",
                            "artifacts": {},
                        }
                        continue

                for split_run in split_runs:
                    run_id = str(split_run["run_id"])
                    segment = str(split_run["segment"])
                    pair_id = str(split_run["pair_id"])
                    window_index = split_run["window_index"]
                    if run_id in used_run_ids or (Path(out_dir) / run_id).exists():
                        row = {
                            "symbol": symbol_str,
                            "timeframe": tf,
                            "split_type": split_type,
                            "segment": segment,
                            "pair_id": pair_id,
                            "window_index": window_index,
                            "status": "FAILED",
                            "run_id": run_id,
                            "config_id": config_id,
                            "config_json": config_json,
                            "error": "run_id_collision",
                            "data_quality": quality,
                            "timestamp_repaired": timestamp_repaired,
                            "timestamp_repaired_reason": timestamp_repaired_reason,
                            "strategy_share_available": False,
                            "strategy_share_error": "",
                            "strategy_counts_json": "{}",
                            "primary_strategy": "",
                            "primary_strategy_share": 0.0,
                            "initial_equity": float(effective_initial_equity),
                            "commission_bps": float(effective_commission_bps),
                            "slippage_bps": float(effective_slippage_bps),
                            "start_at_utc": start_iso,
                            "end_at_utc": end_iso,
                        }
                        rows.append(row)
                        index_payload[run_id] = {
                            "status": "FAILED",
                            "symbol": symbol_str,
                            "timeframe": tf,
                            "split_type": split_type,
                            "segment": segment,
                            "pair_id": pair_id,
                            "window_index": window_index,
                            "config_id": config_id,
                            "config_json": config_json,
                            "error": "run_id_collision",
                            "artifacts": {},
                        }
                        continue
                    used_run_ids.add(run_id)
                    run_dir = Path(out_dir) / run_id

                    try:
                        result = run_backtest(
                            split_run["df"],
                            effective_initial_equity,
                            run_id=run_id,
                            out_dir=out_dir,
                            end_at_utc=None,
                            commission_bps=effective_commission_bps,
                            slippage_bps=effective_slippage_bps,
                        )
                        metrics_payload = json.loads(
                            result.metrics_path.read_text(encoding="utf-8")
                        )
                        manifest_payload = json.loads(
                            result.manifest_path.read_text(encoding="utf-8")
                        )

                        strategy_share_available = True
                        strategy_share_error = ""
                        strategy_counts_json = "{}"
                        primary = ""
                        primary_share = 0.0
                        decisions = 0
                        try:
                            counts, primary_calc, primary_share_calc, decisions_calc = (
                                _strategy_usage(result.decision_records_path)
                            )
                            strategy_counts_json = _canonical_json(counts)
                            primary = primary_calc or ""
                            primary_share = float(primary_share_calc)
                            decisions = int(decisions_calc)
                            overall_decisions += decisions
                            for strategy_id, count in counts.items():
                                overall_strategy_counts[strategy_id] = (
                                    overall_strategy_counts.get(strategy_id, 0) + count
                                )
                        except Exception as exc:
                            strategy_share_available = False
                            strategy_share_error = str(exc) or exc.__class__.__name__

                        row = {
                            "symbol": symbol_str,
                            "timeframe": tf,
                            "split_type": split_type,
                            "segment": segment,
                            "pair_id": pair_id,
                            "window_index": window_index,
                            "status": "OK",
                            "run_id": run_id,
                            "config_id": config_id,
                            "config_json": config_json,
                            "error": None,
                            "data_quality": quality,
                            "timestamp_repaired": timestamp_repaired,
                            "timestamp_repaired_reason": timestamp_repaired_reason,
                            "strategy_share_available": bool(strategy_share_available),
                            "strategy_share_error": strategy_share_error,
                            "strategy_counts_json": strategy_counts_json,
                            "primary_strategy": primary,
                            "primary_strategy_share": float(primary_share),
                            "initial_equity": float(effective_initial_equity),
                            "commission_bps": float(effective_commission_bps),
                            "slippage_bps": float(effective_slippage_bps),
                            "start_at_utc": start_iso,
                            "end_at_utc": end_iso,
                        }
                        for key in (
                            "total_return",
                            "max_drawdown",
                            "num_trades",
                            "win_rate",
                            "avg_win",
                            "avg_loss",
                            "total_costs",
                        ):
                            if key in metrics_payload:
                                row[key] = metrics_payload[key]

                        rows.append(row)
                        index_payload[run_id] = {
                            "status": "OK",
                            "symbol": symbol_str,
                            "timeframe": tf,
                            "split_type": split_type,
                            "segment": segment,
                            "pair_id": pair_id,
                            "window_index": window_index,
                            "config_id": config_id,
                            "config_json": config_json,
                            "artifacts": {
                                "run_dir": str(run_dir),
                                "trades": str(result.trades_path),
                                "metrics": str(result.metrics_path),
                                "run_manifest": str(result.manifest_path),
                                "decision_records": str(result.decision_records_path),
                            },
                            "metrics": {
                                "total_return": metrics_payload.get("total_return"),
                                "max_drawdown": metrics_payload.get("max_drawdown"),
                                "num_trades": metrics_payload.get("num_trades"),
                                "total_costs": metrics_payload.get("total_costs"),
                            },
                            "run_manifest": {
                                "git_sha": manifest_payload.get("git_sha"),
                                "pnl_method": manifest_payload.get("pnl_method"),
                                "end_of_run_position_handling": manifest_payload.get(
                                    "end_of_run_position_handling"
                                ),
                                "strategy_switch_policy": manifest_payload.get(
                                    "strategy_switch_policy"
                                ),
                            },
                        }
                    except Exception as exc:
                        msg = str(exc) or exc.__class__.__name__
                        row = {
                            "symbol": symbol_str,
                            "timeframe": tf,
                            "split_type": split_type,
                            "segment": segment,
                            "pair_id": pair_id,
                            "window_index": window_index,
                            "status": "FAILED",
                            "run_id": run_id,
                            "config_id": config_id,
                            "config_json": config_json,
                            "error": msg,
                            "data_quality": quality,
                            "timestamp_repaired": timestamp_repaired,
                            "timestamp_repaired_reason": timestamp_repaired_reason,
                            "strategy_share_available": False,
                            "strategy_share_error": "",
                            "strategy_counts_json": "{}",
                            "primary_strategy": "",
                            "primary_strategy_share": 0.0,
                            "initial_equity": float(effective_initial_equity),
                            "commission_bps": float(effective_commission_bps),
                            "slippage_bps": float(effective_slippage_bps),
                            "start_at_utc": start_iso,
                            "end_at_utc": end_iso,
                        }
                        rows.append(row)
                        index_payload[run_id] = {
                            "status": "FAILED",
                            "symbol": symbol_str,
                            "timeframe": tf,
                            "split_type": split_type,
                            "segment": segment,
                            "pair_id": pair_id,
                            "window_index": window_index,
                            "config_id": config_id,
                            "config_json": config_json,
                            "error": msg,
                            "artifacts": {},
                        }

                continue
            run_id = run_id_base
            suffix = 2
            while run_id in used_run_ids:
                run_id = f"{run_id_base}_{suffix}"
                suffix += 1
            used_run_ids.add(run_id)
            run_dir = Path(out_dir) / run_id
            if run_dir.exists():
                row = {
                    "symbol": symbol_str,
                    "timeframe": tf,
                    "split_type": "",
                    "segment": "",
                    "pair_id": "",
                    "window_index": None,
                    "status": "FAILED",
                    "run_id": run_id,
                    "config_id": config_id,
                    "config_json": config_json,
                    "error": "run_id_collision",
                    "data_quality": quality,
                    "timestamp_repaired": timestamp_repaired,
                    "timestamp_repaired_reason": timestamp_repaired_reason,
                    "strategy_share_available": False,
                    "strategy_share_error": "",
                    "strategy_counts_json": "{}",
                    "primary_strategy": "",
                    "primary_strategy_share": 0.0,
                    "initial_equity": float(effective_initial_equity),
                    "commission_bps": float(effective_commission_bps),
                    "slippage_bps": float(effective_slippage_bps),
                    "start_at_utc": start_iso,
                    "end_at_utc": end_iso,
                }
                rows.append(row)
                index_payload[run_id] = {
                    "status": "FAILED",
                    "symbol": symbol_str,
                    "timeframe": tf,
                    "split_type": "",
                    "segment": "",
                    "pair_id": "",
                    "window_index": None,
                    "config_id": config_id,
                    "config_json": config_json,
                    "error": "run_id_collision",
                    "artifacts": {},
                }
                continue

            try:
                df_slice = df
                if effective_start is not None:
                    df_slice = df_slice.loc[
                        df_slice.index >= pd.to_datetime(effective_start, utc=True)
                    ]
                result = run_backtest(
                    df_slice,
                    effective_initial_equity,
                    run_id=run_id,
                    out_dir=out_dir,
                    end_at_utc=end_iso,
                    commission_bps=effective_commission_bps,
                    slippage_bps=effective_slippage_bps,
                )
                metrics_payload = json.loads(result.metrics_path.read_text(encoding="utf-8"))
                manifest_payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))

                strategy_share_available = True
                strategy_share_error = ""
                strategy_counts_json = "{}"
                primary = ""
                primary_share = 0.0
                decisions = 0
                try:
                    counts, primary_calc, primary_share_calc, decisions_calc = _strategy_usage(
                        result.decision_records_path
                    )
                    strategy_counts_json = _canonical_json(counts)
                    primary = primary_calc or ""
                    primary_share = float(primary_share_calc)
                    decisions = int(decisions_calc)
                    overall_decisions += decisions
                    for strategy_id, count in counts.items():
                        overall_strategy_counts[strategy_id] = (
                            overall_strategy_counts.get(strategy_id, 0) + count
                        )
                except Exception as exc:
                    strategy_share_available = False
                    strategy_share_error = str(exc) or exc.__class__.__name__

                row = {
                    "symbol": symbol_str,
                    "timeframe": tf,
                    "split_type": "",
                    "segment": "",
                    "pair_id": "",
                    "window_index": None,
                    "status": "OK",
                    "run_id": run_id,
                    "config_id": config_id,
                    "config_json": config_json,
                    "error": None,
                    "data_quality": quality,
                    "timestamp_repaired": timestamp_repaired,
                    "timestamp_repaired_reason": timestamp_repaired_reason,
                    "strategy_share_available": bool(strategy_share_available),
                    "strategy_share_error": strategy_share_error,
                    "strategy_counts_json": strategy_counts_json,
                    "primary_strategy": primary,
                    "primary_strategy_share": float(primary_share),
                    "initial_equity": float(effective_initial_equity),
                    "commission_bps": float(effective_commission_bps),
                    "slippage_bps": float(effective_slippage_bps),
                    "start_at_utc": start_iso,
                    "end_at_utc": end_iso,
                }
                for key in (
                    "total_return",
                    "max_drawdown",
                    "num_trades",
                    "win_rate",
                    "avg_win",
                    "avg_loss",
                    "total_costs",
                ):
                    if key in metrics_payload:
                        row[key] = metrics_payload[key]

                rows.append(row)
                index_payload[run_id] = {
                    "status": "OK",
                    "symbol": symbol_str,
                    "timeframe": tf,
                    "split_type": "",
                    "segment": "",
                    "pair_id": "",
                    "window_index": None,
                    "config_id": config_id,
                    "config_json": config_json,
                    "artifacts": {
                        "run_dir": str(run_dir),
                        "trades": str(result.trades_path),
                        "metrics": str(result.metrics_path),
                        "run_manifest": str(result.manifest_path),
                        "decision_records": str(result.decision_records_path),
                    },
                    "metrics": {
                        "total_return": metrics_payload.get("total_return"),
                        "max_drawdown": metrics_payload.get("max_drawdown"),
                        "num_trades": metrics_payload.get("num_trades"),
                        "total_costs": metrics_payload.get("total_costs"),
                    },
                    "run_manifest": {
                        "git_sha": manifest_payload.get("git_sha"),
                        "pnl_method": manifest_payload.get("pnl_method"),
                        "end_of_run_position_handling": manifest_payload.get(
                            "end_of_run_position_handling"
                        ),
                        "strategy_switch_policy": manifest_payload.get("strategy_switch_policy"),
                    },
                }
            except Exception as exc:
                msg = str(exc) or exc.__class__.__name__
                row = {
                    "symbol": symbol_str,
                    "timeframe": tf,
                    "split_type": "",
                    "segment": "",
                    "pair_id": "",
                    "window_index": None,
                    "status": "FAILED",
                    "run_id": run_id,
                    "config_id": config_id,
                    "config_json": config_json,
                    "error": msg,
                    "data_quality": quality,
                    "timestamp_repaired": timestamp_repaired,
                    "timestamp_repaired_reason": timestamp_repaired_reason,
                    "strategy_share_available": False,
                    "strategy_share_error": "",
                    "strategy_counts_json": "{}",
                    "primary_strategy": "",
                    "primary_strategy_share": 0.0,
                    "initial_equity": float(effective_initial_equity),
                    "commission_bps": float(effective_commission_bps),
                    "slippage_bps": float(effective_slippage_bps),
                    "start_at_utc": start_iso,
                    "end_at_utc": end_iso,
                }
                rows.append(row)
                index_payload[run_id] = {
                    "status": "FAILED",
                    "symbol": symbol_str,
                    "timeframe": tf,
                    "split_type": "",
                    "segment": "",
                    "pair_id": "",
                    "window_index": None,
                    "config_id": config_id,
                    "config_json": config_json,
                    "error": msg,
                    "artifacts": {},
                }

    summary_df = pd.DataFrame(rows)
    if not summary_df.empty:
        summary_df["_segment_order"] = (
            summary_df.get("segment").map({"TRAIN": 0, "TEST": 1}).fillna(2).astype(int)
        )
        summary_df = (
            summary_df.sort_values(
                ["symbol", "timeframe", "config_id", "window_index", "_segment_order", "run_id"],
                kind="mergesort",
            )
            .drop(columns=["_segment_order"])
            .reset_index(drop=True)
        )

    summary_csv_path = batch_dir / "summary.csv"
    summary_json_path = batch_dir / "summary.json"
    index_json_path = batch_dir / "index.json"

    columns: list[str] = [
        "symbol",
        "timeframe",
        "split_type",
        "segment",
        "pair_id",
        "window_index",
        "status",
        "run_id",
        "config_id",
        "config_json",
        "error",
        "timestamp_repaired",
        "timestamp_repaired_reason",
        "strategy_share_available",
        "strategy_share_error",
        "strategy_counts_json",
        "primary_strategy",
        "primary_strategy_share",
        "total_return",
        "max_drawdown",
        "num_trades",
        "win_rate",
        "avg_win",
        "avg_loss",
        "total_costs",
        "initial_equity",
        "commission_bps",
        "slippage_bps",
        "start_at_utc",
        "end_at_utc",
        "data_quality",
    ]
    for col in columns:
        if col not in summary_df.columns:
            summary_df[col] = None
    summary_df[columns].to_csv(summary_csv_path, index=False)

    ok = summary_df[summary_df["status"] == "OK"].copy()
    aggregates: dict[str, Any] = {}
    if not ok.empty:

        def _num(series: pd.Series) -> pd.Series:
            return pd.to_numeric(series, errors="coerce")

        total_return = _num(ok["total_return"])
        max_dd = _num(ok["max_drawdown"])
        total_costs = _num(ok["total_costs"])
        aggregates = {
            "total_return": {
                "mean": float(total_return.mean()),
                "median": float(total_return.median()),
                "min": float(total_return.min()),
                "max": float(total_return.max()),
            },
            "max_drawdown": {
                "mean": float(max_dd.mean()),
                "median": float(max_dd.median()),
                "min": float(max_dd.min()),
                "max": float(max_dd.max()),
            },
            "total_costs": {
                "mean": float(total_costs.mean()),
                "median": float(total_costs.median()),
                "min": float(total_costs.min()),
                "max": float(total_costs.max()),
            },
        }

    top_worst: dict[str, object] = {"top": [], "worst": []}
    if not ok.empty:
        ranked = ok.sort_values(
            ["total_return", "symbol", "run_id"], ascending=[False, True, True], kind="mergesort"
        )
        top = ranked.head(3)[["symbol", "timeframe", "run_id", "total_return"]].to_dict(
            orient="records"
        )
        worst = (
            ranked.tail(3)
            .sort_values(["total_return", "symbol", "run_id"], kind="mergesort")[
                ["symbol", "timeframe", "run_id", "total_return"]
            ]
            .to_dict(orient="records")
        )
        top_worst = {"top": top, "worst": worst}

    overall_strategy_share: dict[str, float] = {}
    if overall_decisions > 0:
        overall_strategy_share = {
            strategy_id: float(count) / float(overall_decisions)
            for strategy_id, count in overall_strategy_counts.items()
        }

    best_worst_by_dataset: dict[str, object] = {}
    if not ok.empty:
        ok_num = ok.copy()
        ok_num["total_return"] = pd.to_numeric(ok_num["total_return"], errors="coerce")
        ok_num["max_drawdown"] = pd.to_numeric(ok_num["max_drawdown"], errors="coerce")
        for dataset_key, group in ok_num.groupby("symbol", sort=True):
            group = group.sort_values(["config_id", "run_id"], kind="mergesort")
            by_ret = group.sort_values(
                ["total_return", "config_id", "run_id"],
                ascending=[False, True, True],
                kind="mergesort",
            )
            max_drawdown_ordering = "smaller_is_better"
            by_dd = group.sort_values(
                ["max_drawdown", "config_id", "run_id"],
                ascending=[True, True, True],
                kind="mergesort",
            )
            best_worst_by_dataset[str(dataset_key)] = {
                "by_total_return": {
                    "best": by_ret.head(1)[
                        ["run_id", "config_id", "total_return", "max_drawdown"]
                    ].to_dict(orient="records")[0],
                    "worst": by_ret.tail(1)[
                        ["run_id", "config_id", "total_return", "max_drawdown"]
                    ].to_dict(orient="records")[0],
                },
                "by_max_drawdown": {
                    "ordering": max_drawdown_ordering,
                    "best": by_dd.head(1)[
                        ["run_id", "config_id", "total_return", "max_drawdown"]
                    ].to_dict(orient="records")[0],
                    "worst": by_dd.tail(1)[
                        ["run_id", "config_id", "total_return", "max_drawdown"]
                    ].to_dict(orient="records")[0],
                },
            }

    overfit_pairs: list[dict[str, object]] = []
    top_by_test_return: list[dict[str, object]] = []
    worst_by_test_drawdown: list[dict[str, object]] = []
    test_drawdown_threshold = 0.2
    if split_type:
        pairs_ok = summary_df[
            (summary_df["status"] == "OK")
            & (summary_df["split_type"] == split_type)
            & (summary_df["pair_id"].astype(str) != "")
        ].copy()
        if not pairs_ok.empty:
            pairs_ok["total_return"] = pd.to_numeric(pairs_ok["total_return"], errors="coerce")
            pairs_ok["max_drawdown"] = pd.to_numeric(pairs_ok["max_drawdown"], errors="coerce")
            if "win_rate" in pairs_ok.columns:
                pairs_ok["win_rate"] = pd.to_numeric(pairs_ok["win_rate"], errors="coerce")

            for pair_id, group in pairs_ok.groupby("pair_id", sort=True):
                train_rows = group[group["segment"] == "TRAIN"]
                test_rows = group[group["segment"] == "TEST"]
                if train_rows.empty or test_rows.empty:
                    continue
                train = train_rows.iloc[0]
                test = test_rows.iloc[0]
                delta_win_rate = None
                if pd.notna(train.get("win_rate")) and pd.notna(test.get("win_rate")):
                    delta_win_rate = float(test["win_rate"] - train["win_rate"])

                overfit_pairs.append(
                    {
                        "pair_id": str(pair_id),
                        "symbol": str(train["symbol"]),
                        "timeframe": str(train["timeframe"]),
                        "config_id": str(train["config_id"]),
                        "window_index": None
                        if pd.isna(train.get("window_index"))
                        else int(train["window_index"]),
                        "run_id_train": str(train["run_id"]),
                        "run_id_test": str(test["run_id"]),
                        "train_total_return": None
                        if pd.isna(train["total_return"])
                        else float(train["total_return"]),
                        "test_total_return": None
                        if pd.isna(test["total_return"])
                        else float(test["total_return"]),
                        "delta_total_return": None
                        if pd.isna(train["total_return"]) or pd.isna(test["total_return"])
                        else float(test["total_return"] - train["total_return"]),
                        "train_max_drawdown": None
                        if pd.isna(train["max_drawdown"])
                        else float(train["max_drawdown"]),
                        "test_max_drawdown": None
                        if pd.isna(test["max_drawdown"])
                        else float(test["max_drawdown"]),
                        "delta_max_drawdown": None
                        if pd.isna(train["max_drawdown"]) or pd.isna(test["max_drawdown"])
                        else float(test["max_drawdown"] - train["max_drawdown"]),
                        "delta_win_rate": delta_win_rate,
                    }
                )

            overfit_pairs = sorted(
                overfit_pairs,
                key=lambda item: (
                    str(item["symbol"]),
                    str(item["config_id"]),
                    -1 if item["window_index"] is None else int(item["window_index"]),
                    str(item["pair_id"]),
                ),
            )

            ranking = [item for item in overfit_pairs if item.get("test_total_return") is not None]
            constrained = [
                item
                for item in ranking
                if item.get("test_max_drawdown") is None
                or float(item["test_max_drawdown"]) <= test_drawdown_threshold
            ]
            if constrained:
                ranking = constrained

            top_by_test_return = sorted(
                ranking,
                key=lambda item: (
                    -float(item["test_total_return"]),
                    str(item["symbol"]),
                    str(item["config_id"]),
                    str(item["pair_id"]),
                ),
            )[:5]

            drawdown_rank = [
                item for item in overfit_pairs if item.get("test_max_drawdown") is not None
            ]
            worst_by_test_drawdown = sorted(
                drawdown_rank,
                key=lambda item: (
                    -float(item["test_max_drawdown"]),
                    str(item["symbol"]),
                    str(item["config_id"]),
                    str(item["pair_id"]),
                ),
            )[:5]

    summary_json = {
        "schema_version": "batch_summary_v2",
        "batch_id": batch_id,
        "timeframe": timeframe,
        "start_at_utc": base_start_iso,
        "end_at_utc": base_end_iso,
        "initial_equity": float(initial_equity),
        "costs": {"commission_bps": float(commission_bps), "slippage_bps": float(slippage_bps)},
        "split": split_cfg,
        "summary_columns": list(columns),
        "counts": {
            "total": int(len(summary_df)),
            "ok": int((summary_df["status"] == "OK").sum()) if not summary_df.empty else 0,
            "failed": int((summary_df["status"] == "FAILED").sum()) if not summary_df.empty else 0,
            "success_count": int((summary_df["status"] == "OK").sum())
            if not summary_df.empty
            else 0,
            "failed_count": int((summary_df["status"] == "FAILED").sum())
            if not summary_df.empty
            else 0,
            "repaired_count": int(summary_df["timestamp_repaired"].fillna(False).astype(bool).sum())
            if not summary_df.empty
            else 0,
        },
        "aggregates": aggregates,
        "top_worst": top_worst,
        "overall_strategy_share": overall_strategy_share,
        "best_worst_by_dataset": best_worst_by_dataset,
        "overfit_pairs": overfit_pairs,
        "test_drawdown_threshold": test_drawdown_threshold,
        "top_by_test_return": top_by_test_return,
        "worst_by_test_drawdown": worst_by_test_drawdown,
    }
    _write_json(summary_json_path, summary_json)

    index_payload_out: dict[str, object] = {
        "schema_version": "batch_index_v2",
        "batch_id": batch_id,
        "batch_dir": str(batch_dir),
        "summary_csv": str(summary_csv_path),
        "summary_json": str(summary_json_path),
        "split": split_cfg,
        "runs": index_payload,
    }
    _write_json(index_json_path, index_payload_out)

    return BatchResult(
        batch_id=batch_id,
        batch_dir=batch_dir,
        summary_csv_path=summary_csv_path,
        summary_json_path=summary_json_path,
        index_json_path=index_json_path,
        summary=summary_df[columns],
        index=index_payload,
    )
