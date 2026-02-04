from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n",
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
) -> BatchResult:
    commission_bps = 0.0
    slippage_bps = 0.0
    if costs is not None:
        commission_bps = float(costs.get("commission_bps", 0.0))
        slippage_bps = float(costs.get("slippage_bps", 0.0))
        if commission_bps < 0.0 or slippage_bps < 0.0:
            raise ValueError("batch_invalid_costs")

    batch_id = _slugify(seed_run_id_prefix) if seed_run_id_prefix else _now_id()
    batch_dir = Path(out_dir) / f"batch_{batch_id}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    start_iso = _iso_utc(start_at_utc) if start_at_utc is not None else None
    end_iso = _iso_utc(end_at_utc) if end_at_utc is not None else None

    rows: list[dict[str, object]] = []
    index_payload: dict[str, dict[str, object]] = {}
    used_run_ids: set[str] = set()

    ordered = sorted(((symbol, timeframe, df) for symbol, df in datasets.items()), key=lambda x: (x[0], x[1]))
    for symbol, tf, df in ordered:
        symbol_str = str(symbol)
        run_id_base = f"{batch_id}_{_slugify(symbol_str)}_{_slugify(tf)}"
        run_id = run_id_base
        suffix = 2
        while run_id in used_run_ids:
            run_id = f"{run_id_base}_{suffix}"
            suffix += 1
        used_run_ids.add(run_id)

        quality, error = _data_quality(df)
        if error is None and quality.get("non_monotonic_timestamps") and isinstance(df, pd.DataFrame):
            df = df.sort_index()

        df_slice = df
        if error is None and isinstance(df, pd.DataFrame):
            if start_at_utc is not None:
                df_slice = df_slice.loc[df_slice.index >= pd.to_datetime(start_at_utc, utc=True)]

        if error is not None:
            row = {
                "symbol": symbol_str,
                "timeframe": tf,
                "status": "FAILED",
                "run_id": run_id,
                "error": error,
                "data_quality": quality,
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
                "error": error,
                "artifacts": {},
            }
            continue

        try:
            result = run_backtest(
                df_slice,
                float(initial_equity),
                run_id=run_id,
                out_dir=out_dir,
                end_at_utc=end_iso,
                commission_bps=float(commission_bps),
                slippage_bps=float(slippage_bps),
            )
            metrics_payload = json.loads(result.metrics_path.read_text(encoding="utf-8"))
            manifest_payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))

            row = {
                "symbol": symbol_str,
                "timeframe": tf,
                "status": "OK",
                "run_id": run_id,
                "error": None,
                "data_quality": quality,
                "initial_equity": float(initial_equity),
                "commission_bps": float(commission_bps),
                "slippage_bps": float(slippage_bps),
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
                "artifacts": {
                    "run_dir": str(Path(out_dir) / run_id),
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
                    "end_of_run_position_handling": manifest_payload.get("end_of_run_position_handling"),
                    "strategy_switch_policy": manifest_payload.get("strategy_switch_policy"),
                },
            }
        except Exception as exc:
            msg = str(exc) or exc.__class__.__name__
            row = {
                "symbol": symbol_str,
                "timeframe": tf,
                "status": "FAILED",
                "run_id": run_id,
                "error": msg,
                "data_quality": quality,
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
                "error": msg,
                "artifacts": {},
            }

    summary_df = pd.DataFrame(rows)
    if not summary_df.empty:
        summary_df = summary_df.sort_values(["symbol", "timeframe", "run_id"], kind="mergesort").reset_index(drop=True)

    summary_csv_path = batch_dir / "summary.csv"
    summary_json_path = batch_dir / "summary.json"
    index_json_path = batch_dir / "index.json"

    columns: list[str] = [
        "symbol",
        "timeframe",
        "status",
        "run_id",
        "error",
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
        ranked = ok.sort_values(["total_return", "symbol", "run_id"], ascending=[False, True, True], kind="mergesort")
        top = ranked.head(3)[["symbol", "timeframe", "run_id", "total_return"]].to_dict(orient="records")
        worst = ranked.tail(3).sort_values(["total_return", "symbol", "run_id"], kind="mergesort")[
            ["symbol", "timeframe", "run_id", "total_return"]
        ].to_dict(orient="records")
        top_worst = {"top": top, "worst": worst}

    summary_json = {
        "batch_id": batch_id,
        "timeframe": timeframe,
        "start_at_utc": start_iso,
        "end_at_utc": end_iso,
        "initial_equity": float(initial_equity),
        "costs": {"commission_bps": float(commission_bps), "slippage_bps": float(slippage_bps)},
        "counts": {
            "total": int(len(summary_df)),
            "ok": int((summary_df["status"] == "OK").sum()) if not summary_df.empty else 0,
            "failed": int((summary_df["status"] == "FAILED").sum()) if not summary_df.empty else 0,
        },
        "aggregates": aggregates,
        "top_worst": top_worst,
    }
    _write_json(summary_json_path, summary_json)

    index_payload_out: dict[str, object] = {
        "batch_id": batch_id,
        "batch_dir": str(batch_dir),
        "summary_csv": str(summary_csv_path),
        "summary_json": str(summary_json_path),
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

