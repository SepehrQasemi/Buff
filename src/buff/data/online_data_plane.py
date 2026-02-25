"""S1 online data plane primitives.

This module implements:
- raw exchange payload capture before parsing
- deterministic canonicalization driven only by raw logs
- gap/late/revision policies with explicit status artifacts
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

from s3.canonical import canonical_json_bytes, canonical_json_text, sha256_hex_bytes

RAW_SCHEMA_VERSION = "s1.raw.capture.v1"
CANONICAL_SCHEMA_VERSION = "s1.canonical.ohlcv.v1"
STATUS_SCHEMA_VERSION = "s1.status.v1"

WS_CHANNEL = "ws"
REST_CHANNEL = "rest"
ALLOWED_CHANNELS = {WS_CHANNEL, REST_CHANNEL}


def _normalize_text_decimal(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _jsonl_bytes(rows: list[Mapping[str, Any]]) -> bytes:
    if not rows:
        return b""
    return b"\n".join(canonical_json_bytes(row) for row in rows) + b"\n"


def _write_bytes(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return sha256_hex_bytes(payload)


def _sha256_file(path: Path) -> str:
    return sha256_hex_bytes(path.read_bytes())


def _stream_id(exchange_id: str, market: str, channel: str) -> str:
    return f"{exchange_id}:{market}:{channel}"


def _payload_to_storage(payload_raw: object) -> tuple[str, str, str]:
    if isinstance(payload_raw, bytes):
        payload_bytes = payload_raw
        payload_text = "base64:" + base64.b64encode(payload_raw).decode("ascii")
        payload_encoding = "base64"
    elif isinstance(payload_raw, str):
        payload_text = payload_raw
        payload_bytes = payload_text.encode("utf-8")
        payload_encoding = "utf-8"
    else:
        payload_text = canonical_json_text(payload_raw)
        payload_bytes = payload_text.encode("utf-8")
        payload_encoding = "json"
    payload_sha256 = sha256_hex_bytes(payload_bytes)
    return payload_text, payload_encoding, payload_sha256


def _payload_bytes_from_record(record: Mapping[str, Any]) -> bytes:
    payload_text = str(record["payload_raw"])
    payload_encoding = str(record.get("payload_encoding", "utf-8"))
    if payload_encoding == "base64":
        if not payload_text.startswith("base64:"):
            raise ValueError("base64 payload must use base64: prefix")
        encoded = payload_text[len("base64:") :]
        return base64.b64decode(encoded.encode("ascii"))
    return payload_text.encode("utf-8")


class RawCaptureWriter:
    """Append-only raw exchange response capture with per-stream ingest sequence."""

    def __init__(self, raw_log_path: Path):
        self.raw_log_path = Path(raw_log_path)
        self._seq_by_stream: dict[str, int] = {}
        self._load_existing_state()

    def _load_existing_state(self) -> None:
        if not self.raw_log_path.exists():
            return
        for line in self.raw_log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            stream = str(record["stream_id"])
            seq = int(record["ingest_seq"])
            prev = self._seq_by_stream.get(stream, 0)
            if seq > prev:
                self._seq_by_stream[stream] = seq

    def append(
        self,
        *,
        exchange_id: str,
        market: str,
        channel: str,
        received_at_ms: int,
        payload_raw: object,
        exchange_event_ts_ms: int | None = None,
    ) -> dict[str, Any]:
        if channel not in ALLOWED_CHANNELS:
            raise ValueError(f"channel must be one of {sorted(ALLOWED_CHANNELS)}")

        stream_id = _stream_id(exchange_id, market, channel)
        ingest_seq = self._seq_by_stream.get(stream_id, 0) + 1
        self._seq_by_stream[stream_id] = ingest_seq

        payload_text, payload_encoding, payload_sha256 = _payload_to_storage(payload_raw)
        record = {
            "schema_version": RAW_SCHEMA_VERSION,
            "stream_id": stream_id,
            "exchange_id": exchange_id,
            "market": market,
            "channel": channel,
            "received_at": int(received_at_ms),
            "exchange_event_ts_ms": (
                int(exchange_event_ts_ms) if exchange_event_ts_ms is not None else None
            ),
            "ingest_seq": ingest_seq,
            "payload_raw": payload_text,
            "payload_encoding": payload_encoding,
            "payload_sha256": payload_sha256,
        }

        line = canonical_json_bytes(record) + b"\n"
        self.raw_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.raw_log_path.open("ab") as fh:
            fh.write(line)
        return record


class OnlineIngestionSession:
    """Capture online WS/REST payloads into immutable raw logs."""

    def __init__(self, *, writer: RawCaptureWriter, exchange_id: str, market: str):
        self._writer = writer
        self._exchange_id = exchange_id
        self._market = market

    def capture_ws(
        self,
        payload_raw: object,
        *,
        received_at_ms: int,
        exchange_event_ts_ms: int | None = None,
    ) -> dict[str, Any]:
        return self._writer.append(
            exchange_id=self._exchange_id,
            market=self._market,
            channel=WS_CHANNEL,
            received_at_ms=received_at_ms,
            payload_raw=payload_raw,
            exchange_event_ts_ms=exchange_event_ts_ms,
        )

    def capture_rest(
        self,
        payload_raw: object,
        *,
        received_at_ms: int,
        exchange_event_ts_ms: int | None = None,
    ) -> dict[str, Any]:
        return self._writer.append(
            exchange_id=self._exchange_id,
            market=self._market,
            channel=REST_CHANNEL,
            received_at_ms=received_at_ms,
            payload_raw=payload_raw,
            exchange_event_ts_ms=exchange_event_ts_ms,
        )


@dataclass(frozen=True)
class CanonicalizationResult:
    run_id: str
    output_dir: Path
    manifest_path: Path
    fail_closed: bool
    raw_log_sha256: str
    config_sha256: str
    artifact_digests: dict[str, str]


def _decode_payload_as_json(record: Mapping[str, Any]) -> dict[str, Any]:
    payload_text = str(record["payload_raw"])
    payload_encoding = str(record.get("payload_encoding", "utf-8"))
    if payload_encoding == "base64":
        if not payload_text.startswith("base64:"):
            raise ValueError("base64 payload must use base64: prefix")
        payload_bytes = base64.b64decode(payload_text[len("base64:") :].encode("ascii"))
        payload_text = payload_bytes.decode("utf-8")
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise ValueError("payload_raw must decode to JSON for canonicalization") from exc
    if not isinstance(payload, dict):
        raise ValueError("payload_raw JSON must be an object")
    return payload


def _extract_decimal(payload: Mapping[str, Any], *keys: str) -> Decimal:
    for key in keys:
        if key in payload:
            value = payload[key]
            try:
                return Decimal(str(value))
            except (InvalidOperation, ValueError) as exc:
                raise ValueError(f"Invalid decimal value for key '{key}'") from exc
    raise ValueError(f"Missing required key(s): {keys}")


def _extract_event_ts_ms(record: Mapping[str, Any], payload: Mapping[str, Any]) -> int:
    for value in (record.get("exchange_event_ts_ms"), payload.get("event_ts_ms"), payload.get("E")):
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("event timestamp must be integer milliseconds") from exc
    raise ValueError("Missing exchange event timestamp in raw record/payload")


def _load_raw_records(raw_log_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in raw_log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parsed = json.loads(line)
        if not isinstance(parsed, dict):
            raise ValueError("raw log entries must be JSON objects")
        payload_bytes = _payload_bytes_from_record(parsed)
        payload_sha256 = sha256_hex_bytes(payload_bytes)
        if payload_sha256 != str(parsed["payload_sha256"]):
            raise ValueError("payload_sha256 mismatch; raw record appears mutated")
        records.append(parsed)
    return records


def _detect_ingest_gaps(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_stream: dict[str, list[int]] = {}
    for record in records:
        stream = str(record["stream_id"])
        by_stream.setdefault(stream, []).append(int(record["ingest_seq"]))

    gaps: list[dict[str, Any]] = []
    for stream_id, seqs in sorted(by_stream.items()):
        if not seqs:
            continue
        expected = 1
        for seq in sorted(seqs):
            if seq != expected:
                gaps.append(
                    {
                        "type": "ingest_seq_gap",
                        "stream_id": stream_id,
                        "expected_ingest_seq": expected,
                        "found_ingest_seq": seq,
                    }
                )
            expected = seq + 1
    return gaps


def _parse_trade_events(
    records: list[dict[str, Any]], timeframe_ms: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    stream_max_bucket: dict[str, int] = {}
    late_events: list[dict[str, Any]] = []
    canonical_events: list[dict[str, Any]] = []

    for record in sorted(records, key=lambda row: (str(row["stream_id"]), int(row["ingest_seq"]))):
        payload = _decode_payload_as_json(record)
        event_ts_ms = _extract_event_ts_ms(record, payload)
        price = _extract_decimal(payload, "price", "p")
        qty = _extract_decimal(payload, "qty", "q", "size", "volume")
        bucket_start_ms = (event_ts_ms // timeframe_ms) * timeframe_ms

        event = {
            "schema_version": CANONICAL_SCHEMA_VERSION,
            "stream_id": str(record["stream_id"]),
            "exchange_id": str(record["exchange_id"]),
            "market": str(record["market"]),
            "channel": str(record["channel"]),
            "ingest_seq": int(record["ingest_seq"]),
            "event_ts_ms": event_ts_ms,
            "bucket_start_ms": bucket_start_ms,
            "price": _normalize_text_decimal(price),
            "qty": _normalize_text_decimal(qty),
            "payload_sha256": str(record["payload_sha256"]),
        }

        stream_id = str(record["stream_id"])
        max_bucket = stream_max_bucket.get(stream_id)
        if max_bucket is not None and bucket_start_ms < max_bucket:
            late_events.append(event)
            continue
        stream_max_bucket[stream_id] = bucket_start_ms
        canonical_events.append(event)

    canonical_events.sort(
        key=lambda row: (int(row["event_ts_ms"]), int(row["ingest_seq"]), str(row["stream_id"]))
    )
    return canonical_events, late_events


def _build_ohlcv_bars(
    canonical_events: list[dict[str, Any]], timeframe_ms: int
) -> list[dict[str, Any]]:
    buckets: dict[int, dict[str, Any]] = {}
    for event in canonical_events:
        bucket_start = int(event["bucket_start_ms"])
        price = Decimal(str(event["price"]))
        qty = Decimal(str(event["qty"]))
        row = buckets.get(bucket_start)
        if row is None:
            row = {
                "schema_version": CANONICAL_SCHEMA_VERSION,
                "exchange_id": event["exchange_id"],
                "market": event["market"],
                "timeframe_ms": timeframe_ms,
                "bucket_start_ms": bucket_start,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": qty,
                "event_count": 1,
                "source_ingest_seq_start": int(event["ingest_seq"]),
                "source_ingest_seq_end": int(event["ingest_seq"]),
                "source_payload_sha256": [str(event["payload_sha256"])],
            }
            buckets[bucket_start] = row
            continue

        row["high"] = max(row["high"], price)
        row["low"] = min(row["low"], price)
        row["close"] = price
        row["volume"] += qty
        row["event_count"] = int(row["event_count"]) + 1
        row["source_ingest_seq_start"] = min(
            int(row["source_ingest_seq_start"]), int(event["ingest_seq"])
        )
        row["source_ingest_seq_end"] = max(
            int(row["source_ingest_seq_end"]), int(event["ingest_seq"])
        )
        row["source_payload_sha256"].append(str(event["payload_sha256"]))

    bars: list[dict[str, Any]] = []
    for bucket_start in sorted(buckets):
        row = buckets[bucket_start]
        bars.append(
            {
                "schema_version": CANONICAL_SCHEMA_VERSION,
                "exchange_id": row["exchange_id"],
                "market": row["market"],
                "timeframe_ms": timeframe_ms,
                "bucket_start_ms": bucket_start,
                "open": _normalize_text_decimal(row["open"]),
                "high": _normalize_text_decimal(row["high"]),
                "low": _normalize_text_decimal(row["low"]),
                "close": _normalize_text_decimal(row["close"]),
                "volume": _normalize_text_decimal(row["volume"]),
                "event_count": row["event_count"],
                "source_ingest_seq_range": {
                    "start": row["source_ingest_seq_start"],
                    "end": row["source_ingest_seq_end"],
                },
                "source_payload_sha256": row["source_payload_sha256"],
            }
        )
    return bars


def _detect_bucket_gaps(
    canonical_events: list[dict[str, Any]], timeframe_ms: int
) -> list[dict[str, Any]]:
    if not canonical_events:
        return []
    observed = sorted({int(event["bucket_start_ms"]) for event in canonical_events})
    min_bucket = observed[0]
    max_bucket = observed[-1]
    observed_set = set(observed)
    gaps: list[dict[str, Any]] = []
    current = min_bucket
    while current <= max_bucket:
        if current not in observed_set:
            gaps.append(
                {
                    "type": "bucket_gap",
                    "bucket_start_ms": current,
                    "timeframe_ms": timeframe_ms,
                }
            )
        current += timeframe_ms
    return gaps


def canonicalize_from_raw_logs(
    *,
    raw_log_path: Path,
    output_dir: Path,
    timeframe_ms: int,
    run_id: str = "",
) -> CanonicalizationResult:
    """Build deterministic canonical events/OHLCV strictly from raw logs."""
    if timeframe_ms <= 0:
        raise ValueError("timeframe_ms must be a positive integer")

    raw_log_path = Path(raw_log_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    records = _load_raw_records(raw_log_path)
    ingest_gaps = _detect_ingest_gaps(records)
    canonical_events, late_events = _parse_trade_events(records, timeframe_ms=timeframe_ms)
    bars = _build_ohlcv_bars(canonical_events, timeframe_ms=timeframe_ms)
    bucket_gaps = _detect_bucket_gaps(canonical_events, timeframe_ms=timeframe_ms)
    all_gaps = ingest_gaps + bucket_gaps

    config_payload = {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "timeframe_ms": timeframe_ms,
        "ordering_rule": ["event_ts_ms", "ingest_seq", "stream_id"],
        "source_rule": "raw_log_only",
        "late_data_policy": "store_raw_emit_revision_candidate_no_silent_mutation",
        "gap_policy": "fail_closed_without_backfill",
    }
    config_sha256 = sha256_hex_bytes(canonical_json_bytes(config_payload))
    raw_log_sha256 = _sha256_file(raw_log_path)
    effective_run_id = run_id
    if not effective_run_id:
        effective_run_id = sha256_hex_bytes(f"{raw_log_sha256}:{config_sha256}".encode("utf-8"))[
            :16
        ]

    canonical_events_path = output_dir / "canonical_events.jsonl"
    canonical_ohlcv_path = output_dir / "canonical_ohlcv.jsonl"
    gap_status_path = output_dir / "gap_status.json"
    revision_status_path = output_dir / "revision_status.json"
    manifest_path = output_dir / "manifest.json"

    gap_status = {
        "schema_version": STATUS_SCHEMA_VERSION,
        "run_id": effective_run_id,
        "policy": "gap",
        "status": "GAP_UNRESOLVED" if all_gaps else "OK",
        "fail_closed": bool(all_gaps),
        "backfill_attempted": False,
        "gaps": all_gaps,
    }
    revision_status = {
        "schema_version": STATUS_SCHEMA_VERSION,
        "run_id": effective_run_id,
        "policy": "revision",
        "status": "REVISION_CANDIDATE" if late_events else "NONE",
        "reason_code": "late_data" if late_events else None,
        "late_event_count": len(late_events),
        "affected_buckets": sorted({int(event["bucket_start_ms"]) for event in late_events}),
        "late_event_payload_sha256": [str(event["payload_sha256"]) for event in late_events],
    }

    events_digest = _write_bytes(canonical_events_path, _jsonl_bytes(canonical_events))
    bars_digest = _write_bytes(canonical_ohlcv_path, _jsonl_bytes(bars))
    gap_digest = _write_bytes(gap_status_path, canonical_json_bytes(gap_status))
    revision_digest = _write_bytes(revision_status_path, canonical_json_bytes(revision_status))

    artifact_digests = {
        canonical_events_path.name: events_digest,
        canonical_ohlcv_path.name: bars_digest,
        gap_status_path.name: gap_digest,
        revision_status_path.name: revision_digest,
    }
    manifest = {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "run_id": effective_run_id,
        "raw_log_sha256": raw_log_sha256,
        "config_sha256": config_sha256,
        "source_rule": "raw_log_only",
        "fail_closed": bool(all_gaps),
        "artifacts": artifact_digests,
        "status": {
            "gap": gap_status["status"],
            "revision": revision_status["status"],
        },
    }
    manifest_digest = _write_bytes(manifest_path, canonical_json_bytes(manifest))
    artifact_digests[manifest_path.name] = manifest_digest

    return CanonicalizationResult(
        run_id=effective_run_id,
        output_dir=output_dir,
        manifest_path=manifest_path,
        fail_closed=bool(all_gaps),
        raw_log_sha256=raw_log_sha256,
        config_sha256=config_sha256,
        artifact_digests=artifact_digests,
    )
