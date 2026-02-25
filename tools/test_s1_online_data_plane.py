from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from buff.data.online_data_plane import RawCaptureWriter, canonicalize_from_raw_logs
from s3.canonical import canonical_json_bytes, sha256_hex_bytes


def _build_raw_record(
    *,
    exchange_id: str,
    market: str,
    channel: str,
    stream_id: str,
    ingest_seq: int,
    received_at: int,
    exchange_event_ts_ms: int,
    price: str,
    qty: str,
) -> dict[str, object]:
    payload = {"event_ts_ms": exchange_event_ts_ms, "price": price, "qty": qty}
    payload_raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {
        "schema_version": "s1.raw.capture.v1",
        "stream_id": stream_id,
        "exchange_id": exchange_id,
        "market": market,
        "channel": channel,
        "received_at": received_at,
        "exchange_event_ts_ms": exchange_event_ts_ms,
        "ingest_seq": ingest_seq,
        "payload_raw": payload_raw,
        "payload_encoding": "utf-8",
        "payload_sha256": sha256_hex_bytes(payload_raw.encode("utf-8")),
    }


def _write_raw_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    lines = [canonical_json_bytes(row) for row in rows]
    payload = b""
    if lines:
        payload = b"\n".join(lines) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def test_replay_determinism(tmp_path: Path) -> None:
    raw_log = tmp_path / "raw" / "events.jsonl"
    writer = RawCaptureWriter(raw_log)

    # Capture raw responses first (before any parsing/canonicalization work).
    writer.append(
        exchange_id="binance",
        market="BTCUSDT",
        channel="ws",
        received_at_ms=1_700_000_000_100,
        exchange_event_ts_ms=1_700_000_000_000,
        payload_raw={"event_ts_ms": 1_700_000_000_000, "price": "100.0", "qty": "1.0"},
    )
    writer.append(
        exchange_id="binance",
        market="BTCUSDT",
        channel="ws",
        received_at_ms=1_700_000_060_100,
        exchange_event_ts_ms=1_700_000_060_000,
        payload_raw={"event_ts_ms": 1_700_000_060_000, "price": "101.0", "qty": "2.0"},
    )

    raw_bytes = raw_log.read_bytes()
    assert raw_bytes
    assert b"payload_raw" in raw_bytes

    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    result_a = canonicalize_from_raw_logs(
        raw_log_path=raw_log,
        output_dir=out_a,
        timeframe_ms=60_000,
        run_id="determinism-fixture",
    )
    result_b = canonicalize_from_raw_logs(
        raw_log_path=raw_log,
        output_dir=out_b,
        timeframe_ms=60_000,
        run_id="determinism-fixture",
    )

    assert raw_log.read_bytes() == raw_bytes
    assert result_a.artifact_digests == result_b.artifact_digests
    assert (out_a / "canonical_events.jsonl").read_bytes() == (
        out_b / "canonical_events.jsonl"
    ).read_bytes()
    assert (out_a / "canonical_ohlcv.jsonl").read_bytes() == (
        out_b / "canonical_ohlcv.jsonl"
    ).read_bytes()
    assert (out_a / "manifest.json").read_bytes() == (out_b / "manifest.json").read_bytes()


def test_gap_detection_fail_closed(tmp_path: Path) -> None:
    raw_log = tmp_path / "raw_gap" / "events.jsonl"
    stream_id = "binance:BTCUSDT:ws"
    rows = [
        _build_raw_record(
            exchange_id="binance",
            market="BTCUSDT",
            channel="ws",
            stream_id=stream_id,
            ingest_seq=1,
            received_at=1_700_000_000_100,
            exchange_event_ts_ms=1_700_000_000_000,
            price="100",
            qty="1",
        ),
        _build_raw_record(
            exchange_id="binance",
            market="BTCUSDT",
            channel="ws",
            stream_id=stream_id,
            ingest_seq=3,
            received_at=1_700_000_120_100,
            exchange_event_ts_ms=1_700_000_120_000,
            price="102",
            qty="1",
        ),
    ]
    _write_raw_jsonl(raw_log, rows)

    result = canonicalize_from_raw_logs(
        raw_log_path=raw_log,
        output_dir=tmp_path / "out_gap",
        timeframe_ms=60_000,
        run_id="gap-fixture",
    )

    assert result.fail_closed is True
    gap_status = json.loads((tmp_path / "out_gap" / "gap_status.json").read_text(encoding="utf-8"))
    assert gap_status["status"] == "GAP_UNRESOLVED"
    assert gap_status["fail_closed"] is True
    assert gap_status["gaps"]
    assert any(gap["type"] == "ingest_seq_gap" for gap in gap_status["gaps"])


def test_late_event_policy(tmp_path: Path) -> None:
    base_raw = tmp_path / "raw_base" / "events.jsonl"
    late_raw = tmp_path / "raw_late" / "events.jsonl"

    base_writer = RawCaptureWriter(base_raw)
    late_writer = RawCaptureWriter(late_raw)

    base_events = [
        (1_700_000_000_000, "100", "1"),
        (1_700_000_060_000, "101", "1"),
    ]
    for ts_ms, price, qty in base_events:
        base_writer.append(
            exchange_id="binance",
            market="BTCUSDT",
            channel="ws",
            received_at_ms=ts_ms + 100,
            exchange_event_ts_ms=ts_ms,
            payload_raw={"event_ts_ms": ts_ms, "price": price, "qty": qty},
        )
        late_writer.append(
            exchange_id="binance",
            market="BTCUSDT",
            channel="ws",
            received_at_ms=ts_ms + 100,
            exchange_event_ts_ms=ts_ms,
            payload_raw={"event_ts_ms": ts_ms, "price": price, "qty": qty},
        )

    # Late arrival for an already-sealed bucket; stored in raw but excluded from canonical bars.
    late_writer.append(
        exchange_id="binance",
        market="BTCUSDT",
        channel="ws",
        received_at_ms=1_700_000_090_000,
        exchange_event_ts_ms=1_700_000_000_000,
        payload_raw={"event_ts_ms": 1_700_000_000_000, "price": "999", "qty": "5"},
    )

    base_result = canonicalize_from_raw_logs(
        raw_log_path=base_raw,
        output_dir=tmp_path / "out_base",
        timeframe_ms=60_000,
        run_id="late-policy",
    )
    late_result = canonicalize_from_raw_logs(
        raw_log_path=late_raw,
        output_dir=tmp_path / "out_late",
        timeframe_ms=60_000,
        run_id="late-policy",
    )

    assert len(late_raw.read_text(encoding="utf-8").splitlines()) == 3
    assert (tmp_path / "out_base" / "canonical_ohlcv.jsonl").read_bytes() == (
        tmp_path / "out_late" / "canonical_ohlcv.jsonl"
    ).read_bytes()

    revision_status = json.loads(
        (tmp_path / "out_late" / "revision_status.json").read_text(encoding="utf-8")
    )
    assert revision_status["status"] == "REVISION_CANDIDATE"
    assert revision_status["reason_code"] == "late_data"
    assert revision_status["late_event_count"] == 1
    assert (
        base_result.artifact_digests["canonical_ohlcv.jsonl"]
        == late_result.artifact_digests["canonical_ohlcv.jsonl"]
    )
