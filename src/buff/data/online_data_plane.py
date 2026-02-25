"""S1 online data plane primitives.

This module implements:
- raw exchange payload capture before parsing
- deterministic canonicalization driven only by raw logs
- gap/late/revision policies with explicit status artifacts
"""

from __future__ import annotations

import base64
import json
import subprocess
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from s3.canonical import canonical_json_bytes, sha256_hex_bytes

RAW_SCHEMA_VERSION = "s1.raw.capture.v2"
CANONICAL_SCHEMA_VERSION = "s1.canonical.ohlcv.v1"
STATUS_SCHEMA_VERSION = "s1.status.v1"
MANIFEST_SCHEMA_VERSION = "s1.manifest.v2"

TRANSPORT_WS = "ws"
TRANSPORT_REST = "rest"
ALLOWED_TRANSPORTS = {TRANSPORT_WS, TRANSPORT_REST}

SOURCE_WS_LIVE = "ws_live"
SOURCE_REST_BACKFILL = "rest_backfill"
ALLOWED_SOURCES = {SOURCE_WS_LIVE, SOURCE_REST_BACKFILL}

ALLOWED_FEED_CHANNELS = {
    "trades",
    "klines",
    "depth",
    "ticker",
    "mark",
    "index",
    "unknown",
}


class BackfillProvider(Protocol):
    def backfill(self, *, symbol: str, start_ms: int, end_ms: int, limit: int) -> list[bytes]:
        """Return raw payload bytes for a requested gap range."""


class NullBackfillProvider:
    def backfill(self, *, symbol: str, start_ms: int, end_ms: int, limit: int) -> list[bytes]:
        return []


@dataclass(frozen=True)
class BackfillPolicy:
    max_attempts: int = 2
    limit: int = 1000


@dataclass(frozen=True)
class CanonicalizationResult:
    run_id: str
    output_dir: Path
    manifest_path: Path
    fail_closed: bool
    fail_reason: str | None
    raw_log_sha256: str
    config_sha256: str
    artifact_digests: dict[str, str]
    artifact_meta: dict[str, dict[str, int | str | None]]


class FailClosedError(RuntimeError):
    def __init__(self, message: str, result: CanonicalizationResult):
        super().__init__(message)
        self.result = result


def _normalize_text_decimal(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    if not rows:
        return b""
    return b"\n".join(canonical_json_bytes(row) for row in rows) + b"\n"


def _write_bytes(path: Path, payload: bytes) -> tuple[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return sha256_hex_bytes(payload), len(payload)


def _sha256_file(path: Path) -> str:
    return sha256_hex_bytes(path.read_bytes())


def _maybe_git_sha() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
    except Exception:
        return None

    if proc.returncode != 0:
        return None
    sha = proc.stdout.strip()
    if len(sha) == 40 and all(ch in "0123456789abcdef" for ch in sha.lower()):
        return sha.lower()
    return None


def _stream_id(exchange_id: str, market: str, transport: str, feed_channel: str) -> str:
    return f"{exchange_id}:{market}:{transport}:{feed_channel}"


def _build_payload_storage(
    *, payload_raw_bytes: bytes | None, payload_raw_text: str | None
) -> tuple[dict[str, str], bytes]:
    if (payload_raw_bytes is None) == (payload_raw_text is None):
        raise ValueError("Exactly one of payload_raw_bytes or payload_raw_text must be provided")

    if payload_raw_bytes is not None:
        if not isinstance(payload_raw_bytes, (bytes, bytearray)):
            raise ValueError("payload_raw_bytes must be bytes")
        payload_bytes = bytes(payload_raw_bytes)
        payload_raw_b64 = base64.b64encode(payload_bytes).decode("ascii")
        return (
            {
                "payload_encoding": "base64",
                "payload_raw_b64": payload_raw_b64,
            },
            payload_bytes,
        )

    if not isinstance(payload_raw_text, str):
        raise ValueError("payload_raw_text must be str")
    payload_text = payload_raw_text
    payload_bytes = payload_text.encode("utf-8")
    return (
        {
            "payload_encoding": "utf-8",
            "payload_raw_text": payload_text,
        },
        payload_bytes,
    )


def _decode_payload_text(record: Mapping[str, Any]) -> str:
    if "payload_raw_b64" in record:
        payload_b64 = str(record["payload_raw_b64"])
        payload_bytes = base64.b64decode(payload_b64.encode("ascii"))
        return payload_bytes.decode("utf-8")
    if "payload_raw_text" in record:
        return str(record["payload_raw_text"])

    # Legacy v1 compatibility path for already persisted artifacts.
    payload_text = str(record.get("payload_raw", ""))
    payload_encoding = str(record.get("payload_encoding", "utf-8"))
    if payload_encoding == "base64":
        if not payload_text.startswith("base64:"):
            raise ValueError("base64 payload must use base64: prefix")
        encoded = payload_text[len("base64:") :]
        payload_bytes = base64.b64decode(encoded.encode("ascii"))
        return payload_bytes.decode("utf-8")
    return payload_text


def _payload_bytes_from_record(record: Mapping[str, Any]) -> bytes:
    if "payload_raw_b64" in record:
        payload_b64 = str(record["payload_raw_b64"])
        return base64.b64decode(payload_b64.encode("ascii"))
    if "payload_raw_text" in record:
        return str(record["payload_raw_text"]).encode("utf-8")

    # Legacy v1 compatibility path for already persisted artifacts.
    payload_text = str(record.get("payload_raw", ""))
    payload_encoding = str(record.get("payload_encoding", "utf-8"))
    if payload_encoding == "base64":
        if not payload_text.startswith("base64:"):
            raise ValueError("base64 payload must use base64: prefix")
        encoded = payload_text[len("base64:") :]
        return base64.b64decode(encoded.encode("ascii"))
    return payload_text.encode("utf-8")


def _validate_transport_source(transport: str, source: str) -> None:
    if transport not in ALLOWED_TRANSPORTS:
        raise ValueError(f"transport must be one of {sorted(ALLOWED_TRANSPORTS)}")
    if source not in ALLOWED_SOURCES:
        raise ValueError(f"source must be one of {sorted(ALLOWED_SOURCES)}")
    if source == SOURCE_WS_LIVE and transport != TRANSPORT_WS:
        raise ValueError("source=ws_live requires transport=ws")
    if source == SOURCE_REST_BACKFILL and transport != TRANSPORT_REST:
        raise ValueError("source=rest_backfill requires transport=rest")


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
        transport: str,
        source: str,
        feed_channel: str,
        received_at_ms: int,
        payload_raw_bytes: bytes | None = None,
        payload_raw_text: str | None = None,
        exchange_event_ts_ms: int | None = None,
    ) -> dict[str, Any]:
        _validate_transport_source(transport, source)
        if feed_channel not in ALLOWED_FEED_CHANNELS:
            raise ValueError(f"feed_channel must be one of {sorted(ALLOWED_FEED_CHANNELS)}")

        stream_id = _stream_id(exchange_id, market, transport, feed_channel)
        ingest_seq = self._seq_by_stream.get(stream_id, 0) + 1
        self._seq_by_stream[stream_id] = ingest_seq

        payload_storage, payload_bytes = _build_payload_storage(
            payload_raw_bytes=payload_raw_bytes,
            payload_raw_text=payload_raw_text,
        )
        payload_sha256 = sha256_hex_bytes(payload_bytes)
        ingest_ts = int(received_at_ms)

        record = {
            "schema_version": RAW_SCHEMA_VERSION,
            "stream_id": stream_id,
            "exchange_id": exchange_id,
            "market": market,
            "transport": transport,
            # Legacy alias retained for compatibility while keeping transport explicit.
            "channel": transport,
            "source": source,
            "feed_channel": feed_channel,
            "event_ts_ingest_ms": ingest_ts,
            # Legacy alias retained for compatibility.
            "received_at": ingest_ts,
            "event_ts_exchange_ms": (
                int(exchange_event_ts_ms) if exchange_event_ts_ms is not None else None
            ),
            # Legacy alias retained for compatibility.
            "exchange_event_ts_ms": (
                int(exchange_event_ts_ms) if exchange_event_ts_ms is not None else None
            ),
            "ingest_seq": ingest_seq,
            **payload_storage,
            "payload_sha256": payload_sha256,
        }

        line = canonical_json_bytes(record) + b"\n"
        self.raw_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.raw_log_path.open("ab") as fh:
            fh.write(line)
        return record


class OnlineIngestionSession:
    """Capture online WS/REST payloads into immutable raw logs."""

    def __init__(
        self,
        *,
        writer: RawCaptureWriter,
        exchange_id: str,
        market: str,
        feed_channel: str = "trades",
    ):
        self._writer = writer
        self._exchange_id = exchange_id
        self._market = market
        self._feed_channel = feed_channel

    def capture_ws(
        self,
        *,
        received_at_ms: int,
        payload_raw_bytes: bytes | None = None,
        payload_raw_text: str | None = None,
        exchange_event_ts_ms: int | None = None,
    ) -> dict[str, Any]:
        return self._writer.append(
            exchange_id=self._exchange_id,
            market=self._market,
            transport=TRANSPORT_WS,
            source=SOURCE_WS_LIVE,
            feed_channel=self._feed_channel,
            received_at_ms=received_at_ms,
            payload_raw_bytes=payload_raw_bytes,
            payload_raw_text=payload_raw_text,
            exchange_event_ts_ms=exchange_event_ts_ms,
        )

    def capture_rest_backfill(
        self,
        *,
        received_at_ms: int,
        payload_raw_bytes: bytes | None = None,
        payload_raw_text: str | None = None,
        exchange_event_ts_ms: int | None = None,
    ) -> dict[str, Any]:
        return self._writer.append(
            exchange_id=self._exchange_id,
            market=self._market,
            transport=TRANSPORT_REST,
            source=SOURCE_REST_BACKFILL,
            feed_channel=self._feed_channel,
            received_at_ms=received_at_ms,
            payload_raw_bytes=payload_raw_bytes,
            payload_raw_text=payload_raw_text,
            exchange_event_ts_ms=exchange_event_ts_ms,
        )

    # Backward-compatible alias.
    def capture_rest(
        self,
        *,
        received_at_ms: int,
        payload_raw_bytes: bytes | None = None,
        payload_raw_text: str | None = None,
        exchange_event_ts_ms: int | None = None,
    ) -> dict[str, Any]:
        return self.capture_rest_backfill(
            received_at_ms=received_at_ms,
            payload_raw_bytes=payload_raw_bytes,
            payload_raw_text=payload_raw_text,
            exchange_event_ts_ms=exchange_event_ts_ms,
        )


def _decode_payload_as_json(record: Mapping[str, Any]) -> dict[str, Any]:
    payload_text = _decode_payload_text(record)
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "payload raw bytes must decode to JSON object for canonicalization"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError("payload raw JSON must be an object")
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
    for value in (
        record.get("event_ts_exchange_ms"),
        record.get("exchange_event_ts_ms"),
        payload.get("event_ts_ms"),
        payload.get("E"),
    ):
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

        required_fields = {
            "schema_version",
            "stream_id",
            "exchange_id",
            "market",
            "ingest_seq",
            "payload_sha256",
            "source",
            "feed_channel",
        }
        missing = sorted(field for field in required_fields if field not in parsed)
        if missing:
            raise ValueError(f"raw log record missing required fields: {missing}")

        payload_bytes = _payload_bytes_from_record(parsed)
        payload_sha256 = sha256_hex_bytes(payload_bytes)
        if payload_sha256 != str(parsed["payload_sha256"]):
            raise ValueError("payload_sha256 mismatch; raw record appears mutated")
        records.append(parsed)
    return records


def _dedupe_records(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    deduped: list[dict[str, Any]] = []
    seen: dict[tuple[str, int], dict[str, Any]] = {}
    duplicate_conflicts: list[dict[str, Any]] = []
    idempotent_duplicate_count = 0

    for record in records:
        key = (str(record["stream_id"]), int(record["ingest_seq"]))
        existing = seen.get(key)
        if existing is None:
            seen[key] = record
            deduped.append(record)
            continue

        if str(existing["payload_sha256"]) == str(record["payload_sha256"]):
            idempotent_duplicate_count += 1
            continue

        duplicate_conflicts.append(
            {
                "type": "duplicate_ingest_seq_conflict",
                "stream_id": key[0],
                "ingest_seq": key[1],
                "existing_payload_sha256": str(existing["payload_sha256"]),
                "conflict_payload_sha256": str(record["payload_sha256"]),
            }
        )
    return deduped, duplicate_conflicts, idempotent_duplicate_count


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
            "transport": str(record.get("transport", record.get("channel", ""))),
            "source": str(record["source"]),
            "feed_channel": str(record["feed_channel"]),
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


def _record_meta(
    sha256: str, size_bytes: int, record_count: int | None
) -> dict[str, int | str | None]:
    return {
        "sha256": sha256,
        "size_bytes": size_bytes,
        "record_count": record_count,
    }


def _build_result(
    *,
    run_id: str,
    output_dir: Path,
    manifest_path: Path,
    fail_closed: bool,
    fail_reason: str | None,
    raw_log_sha256: str,
    config_sha256: str,
    artifact_digests: dict[str, str],
    artifact_meta: dict[str, dict[str, int | str | None]],
) -> CanonicalizationResult:
    return CanonicalizationResult(
        run_id=run_id,
        output_dir=output_dir,
        manifest_path=manifest_path,
        fail_closed=fail_closed,
        fail_reason=fail_reason,
        raw_log_sha256=raw_log_sha256,
        config_sha256=config_sha256,
        artifact_digests=artifact_digests,
        artifact_meta=artifact_meta,
    )


def canonicalize_from_raw_logs(
    *,
    raw_log_path: Path,
    output_dir: Path,
    timeframe_ms: int,
    run_id: str = "",
    backfill_provider: BackfillProvider | None = None,
    backfill_policy: BackfillPolicy | None = None,
) -> CanonicalizationResult:
    """Build deterministic canonical events/OHLCV strictly from raw logs."""
    if timeframe_ms <= 0:
        raise ValueError("timeframe_ms must be a positive integer")

    policy = backfill_policy or BackfillPolicy()
    if policy.max_attempts < 0:
        raise ValueError("backfill max_attempts must be >= 0")
    if policy.limit <= 0:
        raise ValueError("backfill limit must be > 0")
    provider: BackfillProvider = backfill_provider or NullBackfillProvider()

    raw_log_path = Path(raw_log_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if not raw_log_path.exists():
        raise ValueError(f"raw log path does not exist: {raw_log_path}")

    canonical_events_path = output_dir / "canonical_events.jsonl"
    canonical_ohlcv_path = output_dir / "canonical_ohlcv.jsonl"
    gap_status_path = output_dir / "gap_status.json"
    revision_status_path = output_dir / "revision_status.json"
    manifest_path = output_dir / "manifest.json"

    records = _load_raw_records(raw_log_path)
    records, duplicate_conflicts, idempotent_duplicate_count = _dedupe_records(records)

    config_payload = {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "timeframe_ms": timeframe_ms,
        "ordering_rule": ["event_ts_ms", "ingest_seq", "stream_id"],
        "source_rule": "raw_log_only",
        "late_data_policy": "store_raw_emit_revision_candidate_no_silent_mutation",
        "gap_policy": "bounded_backfill_then_fail_closed",
        "backfill_policy": {
            "max_attempts": policy.max_attempts,
            "limit": policy.limit,
        },
    }
    config_sha256 = sha256_hex_bytes(canonical_json_bytes(config_payload))
    raw_log_sha256 = _sha256_file(raw_log_path)
    effective_run_id = run_id
    if not effective_run_id:
        effective_run_id = sha256_hex_bytes(f"{raw_log_sha256}:{config_sha256}".encode("utf-8"))[
            :16
        ]

    attempts = 0
    backfill_attempted = False
    backfill_attempt_log: list[dict[str, Any]] = []
    fail_reason: str | None = None
    backfill_outcome = "not_needed"

    while True:
        ingest_gaps = _detect_ingest_gaps(records)
        canonical_events, late_events = _parse_trade_events(records, timeframe_ms=timeframe_ms)
        bucket_gaps = _detect_bucket_gaps(canonical_events, timeframe_ms=timeframe_ms)
        all_gaps = ingest_gaps + bucket_gaps

        if duplicate_conflicts:
            fail_reason = "duplicate_ingest_seq_conflict"
            backfill_outcome = "unresolved"
            break

        if not all_gaps:
            backfill_outcome = "resolved" if backfill_attempted else "not_needed"
            break

        if attempts >= policy.max_attempts:
            fail_reason = "gap_unresolved_after_backfill_attempts"
            backfill_outcome = "unresolved"
            break

        # Backfill uses deterministic request ordering and writes through the same raw path.
        backfill_attempted = True
        attempts += 1
        attempt_info: dict[str, Any] = {
            "attempt": attempts,
            "requested_bucket_gaps": len(bucket_gaps),
            "inserted_raw_records": 0,
            "provider_calls": [],
        }

        seed_record = records[0] if records else None
        exchange_id = str(seed_record["exchange_id"]) if seed_record is not None else "unknown"
        market = str(seed_record["market"]) if seed_record is not None else "unknown"
        feed_channel = (
            str(seed_record.get("feed_channel", "trades")) if seed_record is not None else "trades"
        )
        writer = RawCaptureWriter(raw_log_path)

        for gap in bucket_gaps:
            start_ms = int(gap["bucket_start_ms"])
            end_ms = start_ms + timeframe_ms - 1
            try:
                payloads = provider.backfill(
                    symbol=market,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    limit=policy.limit,
                )
            except Exception as exc:
                attempt_info["provider_calls"].append(
                    {
                        "start_ms": start_ms,
                        "end_ms": end_ms,
                        "error": str(exc),
                    }
                )
                continue

            if payloads is None:
                payloads = []
            attempt_info["provider_calls"].append(
                {
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "returned_payloads": len(payloads),
                }
            )
            for payload in payloads:
                if not isinstance(payload, (bytes, bytearray)):
                    raise ValueError("backfill provider must return bytes payloads")
                writer.append(
                    exchange_id=exchange_id,
                    market=market,
                    transport=TRANSPORT_REST,
                    source=SOURCE_REST_BACKFILL,
                    feed_channel=feed_channel,
                    received_at_ms=end_ms,
                    payload_raw_bytes=bytes(payload),
                )
                attempt_info["inserted_raw_records"] += 1

        backfill_attempt_log.append(attempt_info)
        records = _load_raw_records(raw_log_path)
        records, duplicate_conflicts, idempotent_duplicate_count = _dedupe_records(records)

    ingest_gaps = _detect_ingest_gaps(records)
    canonical_events, late_events = _parse_trade_events(records, timeframe_ms=timeframe_ms)
    bucket_gaps = _detect_bucket_gaps(canonical_events, timeframe_ms=timeframe_ms)
    all_gaps = ingest_gaps + bucket_gaps
    fail_closed = bool(all_gaps or duplicate_conflicts)

    if fail_closed and fail_reason is None:
        fail_reason = "gap_unresolved"
    if not fail_closed:
        fail_reason = None

    gap_status = {
        "schema_version": STATUS_SCHEMA_VERSION,
        "run_id": effective_run_id,
        "policy": "gap",
        "status": "GAP_UNRESOLVED" if fail_closed else "OK",
        "fail_closed": fail_closed,
        "backfill_attempted": backfill_attempted,
        "attempts": attempts,
        "max_attempts": policy.max_attempts,
        "outcome": backfill_outcome,
        "reason": fail_reason,
        "gaps": all_gaps,
        "duplicate_conflicts": duplicate_conflicts,
        "idempotent_duplicate_count": idempotent_duplicate_count,
        "backfill_attempt_log": backfill_attempt_log,
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

    artifact_digests: dict[str, str] = {}
    artifact_meta: dict[str, dict[str, int | str | None]] = {}

    gap_digest, gap_size = _write_bytes(gap_status_path, canonical_json_bytes(gap_status))
    revision_digest, revision_size = _write_bytes(
        revision_status_path, canonical_json_bytes(revision_status)
    )
    artifact_digests[gap_status_path.name] = gap_digest
    artifact_digests[revision_status_path.name] = revision_digest
    artifact_meta[gap_status_path.name] = _record_meta(gap_digest, gap_size, record_count=None)
    artifact_meta[revision_status_path.name] = _record_meta(
        revision_digest, revision_size, record_count=None
    )

    bars: list[dict[str, Any]] = []
    if fail_closed:
        if canonical_events_path.exists():
            canonical_events_path.unlink()
        if canonical_ohlcv_path.exists():
            canonical_ohlcv_path.unlink()
    else:
        bars = _build_ohlcv_bars(canonical_events, timeframe_ms=timeframe_ms)
        events_payload = _jsonl_bytes(canonical_events)
        bars_payload = _jsonl_bytes(bars)
        events_digest, events_size = _write_bytes(canonical_events_path, events_payload)
        bars_digest, bars_size = _write_bytes(canonical_ohlcv_path, bars_payload)
        artifact_digests[canonical_events_path.name] = events_digest
        artifact_digests[canonical_ohlcv_path.name] = bars_digest
        artifact_meta[canonical_events_path.name] = _record_meta(
            events_digest, events_size, record_count=len(canonical_events)
        )
        artifact_meta[canonical_ohlcv_path.name] = _record_meta(
            bars_digest, bars_size, record_count=len(bars)
        )

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": effective_run_id,
        "raw_schema_version": RAW_SCHEMA_VERSION,
        "canonical_schema_version": CANONICAL_SCHEMA_VERSION,
        "status_schema_version": STATUS_SCHEMA_VERSION,
        "raw_log_sha256": raw_log_sha256,
        "config_sha256": config_sha256,
        "config": config_payload,
        "source_rule": "raw_log_only",
        "ordering_rule": ["event_ts_ms", "ingest_seq", "stream_id"],
        "time_bucket_rule": "utc_epoch_boundary",
        "code_version": {"git_sha": _maybe_git_sha()},
        "record_counts": {
            "raw_records": len(records),
            "canonical_events": len(canonical_events) if not fail_closed else 0,
            "canonical_bars": len(bars) if not fail_closed else 0,
            "late_events": len(late_events),
        },
        "fail_closed": fail_closed,
        "fail_reason": fail_reason,
        "status": {
            "gap": gap_status["status"],
            "revision": revision_status["status"],
        },
        "artifacts": artifact_digests,
        "artifact_meta": artifact_meta,
        "backfill": {
            "attempted": backfill_attempted,
            "attempts": attempts,
            "max_attempts": policy.max_attempts,
            "outcome": backfill_outcome,
        },
        "duplicate_ingest_seq": {
            "idempotent_count": idempotent_duplicate_count,
            "conflict_count": len(duplicate_conflicts),
        },
    }
    manifest_digest, manifest_size = _write_bytes(manifest_path, canonical_json_bytes(manifest))
    artifact_digests[manifest_path.name] = manifest_digest
    artifact_meta[manifest_path.name] = _record_meta(
        manifest_digest, manifest_size, record_count=None
    )

    result = _build_result(
        run_id=effective_run_id,
        output_dir=output_dir,
        manifest_path=manifest_path,
        fail_closed=fail_closed,
        fail_reason=fail_reason,
        raw_log_sha256=raw_log_sha256,
        config_sha256=config_sha256,
        artifact_digests=artifact_digests,
        artifact_meta=artifact_meta,
    )
    if fail_closed:
        raise FailClosedError("fail-closed: canonical publication blocked", result)
    return result
