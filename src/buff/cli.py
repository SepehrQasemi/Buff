"""CLI entrypoint for feature generation."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

import pandas as pd

from buff.features.metadata import build_metadata, sha256_file, write_json
from buff.features.registry import FEATURES
from buff.features.runner import run_features
from audit.bundle import BundleError, build_bundle
from audit.verify import verify_bundle
from execution.idempotency_inspect import (
    IdempotencyInspectError,
    fetch_all_records,
    fetch_record,
    open_idempotency_db,
)
from execution.idempotency_sqlite import default_idempotency_db_path
from risk.evaluator import evaluate_risk_report
from risk.report import write_risk_report
from risk.types import RiskContext


def _detect_input_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".parquet":
        return "parquet"
    raise ValueError("Input must be .csv or .parquet")


def _read_input(path: Path, input_format: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Input not found: {path}")
    if input_format == "csv":
        return pd.read_csv(path)
    if input_format == "parquet":
        return pd.read_parquet(path, engine="pyarrow")
    raise ValueError("Input format must be csv or parquet")


def _parse_utc(value: str) -> datetime:
    ts = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(ts)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_timestamp_column(df: pd.DataFrame) -> pd.DataFrame:
    if "timestamp" in df.columns:
        return df
    if "ts" in df.columns:
        out = df.copy()
        out["timestamp"] = out["ts"]
        return out
    return df


def main() -> None:
    parser = argparse.ArgumentParser(prog="buff")
    subparsers = parser.add_subparsers(dest="command", required=True)

    features_parser = subparsers.add_parser("features", help="Generate features")
    features_parser.add_argument("input_path")
    features_parser.add_argument("output_path")
    features_parser.add_argument("--meta", dest="meta_path")
    features_parser.add_argument("--symbol", type=str, default=None, help="Symbol label")
    features_parser.add_argument("--timeframe", type=str, default=None, help="Timeframe label")
    features_parser.add_argument("--run_id", type=str, default=None, help="Optional run id")

    idempotency_parser = subparsers.add_parser("idempotency", help="Inspect idempotency store")
    idempotency_sub = idempotency_parser.add_subparsers(dest="idempo_cmd", required=True)

    idempo_list = idempotency_sub.add_parser("list", help="List idempotency records")
    idempo_list.add_argument("--db-path", dest="db_path", type=str, default=None)
    idempo_list.add_argument("--as-of-utc", dest="as_of_utc", type=str, default=None)
    idempo_list.add_argument("--json", dest="json_out", action="store_true")

    idempo_show = idempotency_sub.add_parser("show", help="Show a single record")
    idempo_show.add_argument("key")
    idempo_show.add_argument("--db-path", dest="db_path", type=str, default=None)

    idempo_export = idempotency_sub.add_parser("export", help="Export idempotency records")
    idempo_export.add_argument("--db-path", dest="db_path", type=str, default=None)
    idempo_export.add_argument("--out", dest="out_path", type=str, default=None)

    audit_parser = subparsers.add_parser("audit", help="Audit tools")
    audit_sub = audit_parser.add_subparsers(dest="audit_cmd", required=True)
    audit_bundle = audit_sub.add_parser("bundle", help="Export audit bundle")
    audit_bundle.add_argument("--out", required=True)
    audit_bundle.add_argument("--format", choices=["zip", "dir"], default="zip")
    audit_bundle.add_argument("--as-of-utc", dest="as_of_utc", type=str, default=None)
    audit_bundle.add_argument("--db-path", dest="db_path", type=str, default=None)
    audit_bundle.add_argument("--decision-records", dest="decision_records", type=str, default=None)
    audit_bundle.add_argument("--include-logs", dest="include_logs", nargs="*", default=[])
    audit_verify = audit_sub.add_parser("verify", help="Verify audit bundle")
    audit_verify.add_argument("--bundle", required=True)
    audit_verify.add_argument("--format", choices=["auto", "zip", "dir"], default="auto")
    audit_verify.add_argument("--strict", action="store_true")
    audit_verify.add_argument("--json", dest="json_out", action="store_true")
    audit_verify.add_argument("--as-of-utc", dest="as_of_utc", type=str, default=None)

    args = parser.parse_args()
    if args.command == "idempotency":
        _run_idempotency(args)
        return
    if args.command == "audit":
        _run_audit(args)
        return
    if args.command != "features":
        raise SystemExit(2)

    input_path = Path(args.input_path)
    output_path = Path(args.output_path)
    meta_path = Path(args.meta_path) if args.meta_path else Path(f"{output_path}.meta.json")

    input_format = _detect_input_format(input_path)
    input_sha256 = sha256_file(input_path)
    df = _read_input(input_path, input_format)
    feature_input = _normalize_timestamp_column(df)

    out = run_features(feature_input)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(output_path, engine="pyarrow")

    output_sha256 = sha256_file(output_path)
    feature_params = {}
    for name, spec in FEATURES.items():
        params = dict(spec["params"])
        kind = spec["kind"]
        if kind in {"ema", "sma", "std", "bbands"}:
            params["_valid_from"] = params["period"] - 1
        elif kind in {"rsi", "atr"}:
            params["_valid_from"] = params["period"]
        elif kind == "macd":
            params["_valid_from"] = params["slow"] + params["signal"] - 2
        else:
            raise ValueError(f"Unknown feature kind: {kind}")
        feature_params[name] = params

    metadata = build_metadata(
        input_path=str(input_path),
        input_format=input_format,
        input_sha256=input_sha256,
        output_path=str(output_path),
        output_sha256=output_sha256,
        row_count=int(out.shape[0]),
        columns=list(out.columns),
        features=list(FEATURES.keys()),
        feature_params=feature_params,
    )
    write_json(meta_path, metadata)

    report = evaluate_risk_report(
        out,
        feature_input,
        context=RiskContext(
            run_id=args.run_id,
            workspace=None,
            symbol=args.symbol,
            timeframe=args.timeframe,
        ),
    )
    write_risk_report(report, mode="system")


def _resolve_db_path(arg: str | None) -> Path:
    return Path(arg) if arg else default_idempotency_db_path()


def _open_db_or_exit(path: Path):
    try:
        return open_idempotency_db(str(path))
    except (FileNotFoundError, IdempotencyInspectError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def _run_idempotency(args: argparse.Namespace) -> None:
    db_path = _resolve_db_path(getattr(args, "db_path", None))
    if args.idempo_cmd == "list":
        _cmd_idempotency_list(db_path, args)
        return
    if args.idempo_cmd == "show":
        _cmd_idempotency_show(db_path, args.key)
        return
    if args.idempo_cmd == "export":
        _cmd_idempotency_export(db_path, args.out_path)
        return
    raise SystemExit(2)


def _cmd_idempotency_list(path: Path, args: argparse.Namespace) -> None:
    conn = _open_db_or_exit(path)
    try:
        rows = fetch_all_records(conn)
    finally:
        conn.close()

    as_of = None
    if args.as_of_utc:
        try:
            as_of = _parse_utc(args.as_of_utc)
        except ValueError as exc:
            print(f"error: invalid as-of-utc: {args.as_of_utc}", file=sys.stderr)
            raise SystemExit(1) from exc

    if args.json_out:
        payload: list[dict[str, Any]] = []
        for key, record in rows:
            reserved_at = record.get("reserved_at_utc")
            age = None
            if as_of is not None and isinstance(reserved_at, str) and reserved_at:
                age = int((as_of - _parse_utc(reserved_at)).total_seconds())
            payload.append(
                {
                    "key": key,
                    "status": record.get("status"),
                    "reserved_at_utc": reserved_at,
                    "age_seconds": age,
                }
            )
        print(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return

    header = ["key", "status", "reserved_at_utc", "age_seconds"]
    print("\t".join(header))
    for key, record in rows:
        display_key = key[:16]
        status = str(record.get("status", ""))
        reserved_at = record.get("reserved_at_utc") or ""
        age = "NA"
        if as_of is not None and isinstance(reserved_at, str) and reserved_at:
            age = str(int((as_of - _parse_utc(reserved_at)).total_seconds()))
        print(f"{display_key}\t{status}\t{reserved_at}\t{age}")


def _cmd_idempotency_show(path: Path, key: str) -> None:
    conn = _open_db_or_exit(path)
    try:
        record = fetch_record(conn, key)
    finally:
        conn.close()
    if record is None:
        print(f"error: idempotency key not found: {key}", file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(record, sort_keys=True, indent=2, ensure_ascii=False))


def _cmd_idempotency_export(path: Path, out_path: str | None) -> None:
    conn = _open_db_or_exit(path)
    try:
        rows = fetch_all_records(conn)
    finally:
        conn.close()

    lines = [
        json.dumps(
            {"key": key, "record": record},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        for key, record in rows
    ]
    payload = "\n".join(lines) + ("\n" if lines else "")

    if out_path:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")
        return
    print(payload, end="")


def _run_audit(args: argparse.Namespace) -> None:
    if args.audit_cmd == "verify":
        report = verify_bundle(
            path=Path(args.bundle),
            fmt=args.format,
            strict=args.strict,
            as_of_utc=args.as_of_utc,
        )
        if args.json_out:
            print(json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        else:
            if report["ok"]:
                print("audit_verify: ok")
            else:
                print("audit_verify: failed")
            for item in report["errors"]:
                print(f"error: {item['code']} {item.get('path', '')}".strip(), file=sys.stderr)
            for item in report["warnings"]:
                print(f"warning: {item['code']} {item.get('path', '')}".strip(), file=sys.stderr)
        raise SystemExit(0 if report["ok"] else 1)

    if args.audit_cmd != "bundle":
        raise SystemExit(2)
    db_path = _resolve_db_path(args.db_path)
    if args.decision_records:
        decision_records = Path(args.decision_records)
    else:
        decision_records = Path("workspaces")
    out_path = Path(args.out)
    include_logs = [Path(path) for path in args.include_logs]
    try:
        build_bundle(
            out_path=out_path,
            fmt=args.format,
            as_of_utc=args.as_of_utc,
            db_path=db_path,
            decision_records_path=decision_records,
            include_logs=include_logs,
        )
    except BundleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(f"bundle_written: {out_path}")


if __name__ == "__main__":
    main()
