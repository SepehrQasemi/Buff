from __future__ import annotations

import base64
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from buff.data.online_data_plane import (
    BackfillPolicy,
    FailClosedError,
    RawCaptureWriter,
    canonicalize_from_raw_logs,
)
from s3.canonical import canonical_json_bytes, sha256_hex_bytes


def _payload_bytes(event_ts_ms: int, price: str, qty: str, *, pretty: bool = False) -> bytes:
    payload = {"event_ts_ms": event_ts_ms, "price": price, "qty": qty}
    if pretty:
        return json.dumps(payload, indent=2, sort_keys=False).encode("utf-8")
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _stream_id(
    exchange_id: str = "binance",
    market: str = "BTCUSDT",
    transport: str = "ws",
    feed_channel: str = "trades",
) -> str:
    return f"{exchange_id}:{market}:{transport}:{feed_channel}"


def _raw_record(
    *,
    ingest_seq: int,
    event_ts_ms: int,
    received_at_ms: int,
    payload_bytes: bytes,
    exchange_id: str = "binance",
    market: str = "BTCUSDT",
    transport: str = "ws",
    source: str = "ws_live",
    feed_channel: str = "trades",
) -> dict[str, object]:
    payload_raw_text = payload_bytes.decode("utf-8")
    return {
        "schema_version": "s1.raw.capture.v2",
        "stream_id": _stream_id(
            exchange_id=exchange_id,
            market=market,
            transport=transport,
            feed_channel=feed_channel,
        ),
        "exchange_id": exchange_id,
        "market": market,
        "transport": transport,
        "channel": transport,
        "source": source,
        "feed_channel": feed_channel,
        "event_ts_ingest_ms": received_at_ms,
        "received_at": received_at_ms,
        "event_ts_exchange_ms": event_ts_ms,
        "exchange_event_ts_ms": event_ts_ms,
        "ingest_seq": ingest_seq,
        "payload_encoding": "utf-8",
        "payload_raw_text": payload_raw_text,
        "payload_sha256": sha256_hex_bytes(payload_bytes),
    }


def _write_raw_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    lines = [canonical_json_bytes(row) for row in rows]
    payload = b""
    if lines:
        payload = b"\n".join(lines) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


class FakeBackfillProvider:
    def __init__(self, responses: list[list[bytes]] | None = None):
        self._responses = list(responses or [])
        self.calls: list[dict[str, int | str]] = []

    def backfill(self, *, symbol: str, start_ms: int, end_ms: int, limit: int) -> list[bytes]:
        self.calls.append(
            {
                "symbol": symbol,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "limit": limit,
            }
        )
        if self._responses:
            return self._responses.pop(0)
        return []


def _assert_identical_artifacts(dir_a: Path, dir_b: Path, names: list[str]) -> None:
    for name in names:
        a = dir_a / name
        b = dir_b / name
        assert a.read_bytes() == b.read_bytes()
        assert a.stat().st_size == b.stat().st_size
        if name.endswith(".jsonl"):
            assert len(a.read_text(encoding="utf-8").splitlines()) == len(
                b.read_text(encoding="utf-8").splitlines()
            )


def test_raw_capture_rejects_object_payload(tmp_path: Path) -> None:
    writer = RawCaptureWriter(tmp_path / "raw.jsonl")

    with pytest.raises(ValueError, match="payload_raw_text must be str"):
        writer.append(
            exchange_id="binance",
            market="BTCUSDT",
            transport="ws",
            source="ws_live",
            feed_channel="trades",
            received_at_ms=1,
            payload_raw_text={"event_ts_ms": 1},  # type: ignore[arg-type]
        )


def test_payload_sha256_uses_exact_raw_bytes(tmp_path: Path) -> None:
    raw_log = tmp_path / "raw_whitespace.jsonl"
    writer = RawCaptureWriter(raw_log)

    payload_compact = _payload_bytes(1_700_000_000_000, "100", "1", pretty=False)
    payload_pretty = _payload_bytes(1_700_000_000_000, "100", "1", pretty=True)

    rec_compact = writer.append(
        exchange_id="binance",
        market="BTCUSDT",
        transport="ws",
        source="ws_live",
        feed_channel="trades",
        received_at_ms=10,
        exchange_event_ts_ms=1_700_000_000_000,
        payload_raw_bytes=payload_compact,
    )
    rec_pretty = writer.append(
        exchange_id="binance",
        market="BTCUSDT",
        transport="ws",
        source="ws_live",
        feed_channel="trades",
        received_at_ms=20,
        exchange_event_ts_ms=1_700_000_000_000,
        payload_raw_bytes=payload_pretty,
    )

    assert rec_compact["payload_sha256"] != rec_pretty["payload_sha256"]
    assert rec_compact["payload_sha256"] == sha256_hex_bytes(payload_compact)
    assert rec_pretty["payload_sha256"] == sha256_hex_bytes(payload_pretty)


def test_raw_roundtrip_bytes_fidelity(tmp_path: Path) -> None:
    raw_log = tmp_path / "raw_roundtrip.jsonl"
    writer = RawCaptureWriter(raw_log)
    payload = b'{"event_ts_ms":1700000000000,"price":"100","qty":"1"}\n\x00binary-tail'

    writer.append(
        exchange_id="binance",
        market="BTCUSDT",
        transport="ws",
        source="ws_live",
        feed_channel="trades",
        received_at_ms=1,
        exchange_event_ts_ms=1_700_000_000_000,
        payload_raw_bytes=payload,
    )

    line = raw_log.read_text(encoding="utf-8").splitlines()[0]
    record = json.loads(line)
    decoded = base64.b64decode(record["payload_raw_b64"].encode("ascii"))
    assert decoded == payload


def test_raw_schema_includes_source_and_feed_channel(tmp_path: Path) -> None:
    raw_log = tmp_path / "raw_schema.jsonl"
    writer = RawCaptureWriter(raw_log)

    record = writer.append(
        exchange_id="binance",
        market="BTCUSDT",
        transport="rest",
        source="rest_backfill",
        feed_channel="trades",
        received_at_ms=10,
        exchange_event_ts_ms=1_700_000_000_000,
        payload_raw_bytes=_payload_bytes(1_700_000_000_000, "100", "1"),
    )

    assert record["source"] == "rest_backfill"
    assert record["feed_channel"] == "trades"
    assert record["transport"] == "rest"

    loaded = json.loads(raw_log.read_text(encoding="utf-8").splitlines()[0])
    assert loaded["source"] in {"ws_live", "rest_backfill"}
    assert loaded["feed_channel"] in {
        "trades",
        "klines",
        "depth",
        "ticker",
        "mark",
        "index",
        "unknown",
    }


def test_replay_determinism(tmp_path: Path) -> None:
    raw_log = tmp_path / "raw_det" / "events.jsonl"
    writer = RawCaptureWriter(raw_log)
    writer.append(
        exchange_id="binance",
        market="BTCUSDT",
        transport="ws",
        source="ws_live",
        feed_channel="trades",
        received_at_ms=1_700_000_000_100,
        exchange_event_ts_ms=1_700_000_000_000,
        payload_raw_bytes=_payload_bytes(1_700_000_000_000, "100.0", "1.0"),
    )
    writer.append(
        exchange_id="binance",
        market="BTCUSDT",
        transport="ws",
        source="ws_live",
        feed_channel="trades",
        received_at_ms=1_700_000_060_100,
        exchange_event_ts_ms=1_700_000_060_000,
        payload_raw_bytes=_payload_bytes(1_700_000_060_000, "101.0", "2.0"),
    )

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

    assert result_a.artifact_digests == result_b.artifact_digests
    _assert_identical_artifacts(
        out_a,
        out_b,
        [
            "canonical_events.jsonl",
            "canonical_ohlcv.jsonl",
            "manifest.json",
            "gap_status.json",
            "revision_status.json",
        ],
    )


def test_replay_identical_sizes_and_counts(tmp_path: Path) -> None:
    raw_log = tmp_path / "raw_size" / "events.jsonl"
    writer = RawCaptureWriter(raw_log)
    for i, ts_ms in enumerate([1_700_000_000_000, 1_700_000_060_000, 1_700_000_120_000], start=1):
        writer.append(
            exchange_id="binance",
            market="BTCUSDT",
            transport="ws",
            source="ws_live",
            feed_channel="trades",
            received_at_ms=ts_ms + 100,
            exchange_event_ts_ms=ts_ms,
            payload_raw_bytes=_payload_bytes(ts_ms, str(100 + i), "1"),
        )

    out_a = tmp_path / "size_a"
    out_b = tmp_path / "size_b"
    canonicalize_from_raw_logs(
        raw_log_path=raw_log, output_dir=out_a, timeframe_ms=60_000, run_id="size"
    )
    canonicalize_from_raw_logs(
        raw_log_path=raw_log, output_dir=out_b, timeframe_ms=60_000, run_id="size"
    )

    _assert_identical_artifacts(
        out_a,
        out_b,
        ["canonical_events.jsonl", "canonical_ohlcv.jsonl", "manifest.json"],
    )


def test_gap_triggers_backfill_attempts(tmp_path: Path) -> None:
    raw_log = tmp_path / "raw_gap_attempts" / "events.jsonl"
    writer = RawCaptureWriter(raw_log)
    writer.append(
        exchange_id="binance",
        market="BTCUSDT",
        transport="ws",
        source="ws_live",
        feed_channel="trades",
        received_at_ms=1_700_000_000_100,
        exchange_event_ts_ms=1_700_000_000_000,
        payload_raw_bytes=_payload_bytes(1_700_000_000_000, "100", "1"),
    )
    writer.append(
        exchange_id="binance",
        market="BTCUSDT",
        transport="ws",
        source="ws_live",
        feed_channel="trades",
        received_at_ms=1_700_000_120_100,
        exchange_event_ts_ms=1_700_000_120_000,
        payload_raw_bytes=_payload_bytes(1_700_000_120_000, "102", "1"),
    )

    provider = FakeBackfillProvider(responses=[[]])
    with pytest.raises(FailClosedError) as exc:
        canonicalize_from_raw_logs(
            raw_log_path=raw_log,
            output_dir=tmp_path / "out_gap_attempts",
            timeframe_ms=60_000,
            run_id="gap-attempts",
            backfill_provider=provider,
            backfill_policy=BackfillPolicy(max_attempts=1, limit=10),
        )

    gap_status = json.loads(
        (tmp_path / "out_gap_attempts" / "gap_status.json").read_text(encoding="utf-8")
    )
    assert gap_status["backfill_attempted"] is True
    assert gap_status["attempts"] == 1
    assert gap_status["outcome"] == "unresolved"
    assert provider.calls
    assert exc.value.result.fail_closed is True


def test_gap_unresolved_after_n_attempts_emits_gap_unresolved(tmp_path: Path) -> None:
    raw_log = tmp_path / "raw_gap_unresolved" / "events.jsonl"
    writer = RawCaptureWriter(raw_log)
    writer.append(
        exchange_id="binance",
        market="BTCUSDT",
        transport="ws",
        source="ws_live",
        feed_channel="trades",
        received_at_ms=1_700_000_000_100,
        exchange_event_ts_ms=1_700_000_000_000,
        payload_raw_bytes=_payload_bytes(1_700_000_000_000, "100", "1"),
    )
    writer.append(
        exchange_id="binance",
        market="BTCUSDT",
        transport="ws",
        source="ws_live",
        feed_channel="trades",
        received_at_ms=1_700_000_120_100,
        exchange_event_ts_ms=1_700_000_120_000,
        payload_raw_bytes=_payload_bytes(1_700_000_120_000, "102", "1"),
    )

    provider = FakeBackfillProvider(responses=[[], []])
    with pytest.raises(FailClosedError):
        canonicalize_from_raw_logs(
            raw_log_path=raw_log,
            output_dir=tmp_path / "out_gap_unresolved",
            timeframe_ms=60_000,
            run_id="gap-unresolved",
            backfill_provider=provider,
            backfill_policy=BackfillPolicy(max_attempts=2, limit=10),
        )

    gap_status = json.loads(
        (tmp_path / "out_gap_unresolved" / "gap_status.json").read_text(encoding="utf-8")
    )
    assert gap_status["status"] == "GAP_UNRESOLVED"
    assert gap_status["fail_closed"] is True
    assert gap_status["reason"] == "gap_unresolved_after_backfill_attempts"
    assert gap_status["attempts"] == 2


def test_gap_resolved_clears_fail_closed(tmp_path: Path) -> None:
    raw_log = tmp_path / "raw_gap_resolved" / "events.jsonl"
    writer = RawCaptureWriter(raw_log)
    writer.append(
        exchange_id="binance",
        market="BTCUSDT",
        transport="ws",
        source="ws_live",
        feed_channel="trades",
        received_at_ms=1_700_000_000_100,
        exchange_event_ts_ms=1_700_000_000_000,
        payload_raw_bytes=_payload_bytes(1_700_000_000_000, "100", "1"),
    )
    writer.append(
        exchange_id="binance",
        market="BTCUSDT",
        transport="ws",
        source="ws_live",
        feed_channel="trades",
        received_at_ms=1_700_000_120_100,
        exchange_event_ts_ms=1_700_000_120_000,
        payload_raw_bytes=_payload_bytes(1_700_000_120_000, "102", "1"),
    )

    missing_bucket_payload = _payload_bytes(1_700_000_060_000, "101", "1")
    provider = FakeBackfillProvider(responses=[[missing_bucket_payload]])
    result = canonicalize_from_raw_logs(
        raw_log_path=raw_log,
        output_dir=tmp_path / "out_gap_resolved",
        timeframe_ms=60_000,
        run_id="gap-resolved",
        backfill_provider=provider,
        backfill_policy=BackfillPolicy(max_attempts=2, limit=10),
    )

    assert result.fail_closed is False
    gap_status = json.loads(
        (tmp_path / "out_gap_resolved" / "gap_status.json").read_text(encoding="utf-8")
    )
    assert gap_status["status"] == "OK"
    assert gap_status["outcome"] == "resolved"
    assert gap_status["attempts"] == 1
    raw_lines = [json.loads(line) for line in raw_log.read_text(encoding="utf-8").splitlines()]
    assert any(line["source"] == "rest_backfill" for line in raw_lines)


def test_unresolved_gap_blocks_canonical_publication(tmp_path: Path) -> None:
    raw_log = tmp_path / "raw_block" / "events.jsonl"
    writer = RawCaptureWriter(raw_log)
    writer.append(
        exchange_id="binance",
        market="BTCUSDT",
        transport="ws",
        source="ws_live",
        feed_channel="trades",
        received_at_ms=1_700_000_000_100,
        exchange_event_ts_ms=1_700_000_000_000,
        payload_raw_bytes=_payload_bytes(1_700_000_000_000, "100", "1"),
    )
    writer.append(
        exchange_id="binance",
        market="BTCUSDT",
        transport="ws",
        source="ws_live",
        feed_channel="trades",
        received_at_ms=1_700_000_120_100,
        exchange_event_ts_ms=1_700_000_120_000,
        payload_raw_bytes=_payload_bytes(1_700_000_120_000, "102", "1"),
    )

    with pytest.raises(FailClosedError):
        canonicalize_from_raw_logs(
            raw_log_path=raw_log,
            output_dir=tmp_path / "out_block",
            timeframe_ms=60_000,
            run_id="block",
            backfill_provider=FakeBackfillProvider(responses=[[]]),
            backfill_policy=BackfillPolicy(max_attempts=1, limit=10),
        )

    assert not (tmp_path / "out_block" / "canonical_events.jsonl").exists()
    assert not (tmp_path / "out_block" / "canonical_ohlcv.jsonl").exists()
    assert (tmp_path / "out_block" / "gap_status.json").exists()
    assert (tmp_path / "out_block" / "manifest.json").exists()


def test_late_event_policy(tmp_path: Path) -> None:
    base_raw = tmp_path / "raw_base" / "events.jsonl"
    late_raw = tmp_path / "raw_late" / "events.jsonl"

    base_writer = RawCaptureWriter(base_raw)
    late_writer = RawCaptureWriter(late_raw)

    for ts_ms, price in [(1_700_000_000_000, "100"), (1_700_000_060_000, "101")]:
        payload = _payload_bytes(ts_ms, price, "1")
        base_writer.append(
            exchange_id="binance",
            market="BTCUSDT",
            transport="ws",
            source="ws_live",
            feed_channel="trades",
            received_at_ms=ts_ms + 100,
            exchange_event_ts_ms=ts_ms,
            payload_raw_bytes=payload,
        )
        late_writer.append(
            exchange_id="binance",
            market="BTCUSDT",
            transport="ws",
            source="ws_live",
            feed_channel="trades",
            received_at_ms=ts_ms + 100,
            exchange_event_ts_ms=ts_ms,
            payload_raw_bytes=payload,
        )

    late_writer.append(
        exchange_id="binance",
        market="BTCUSDT",
        transport="ws",
        source="ws_live",
        feed_channel="trades",
        received_at_ms=1_700_000_090_000,
        exchange_event_ts_ms=1_700_000_000_000,
        payload_raw_bytes=_payload_bytes(1_700_000_000_000, "999", "5"),
    )

    canonicalize_from_raw_logs(
        raw_log_path=base_raw,
        output_dir=tmp_path / "out_base",
        timeframe_ms=60_000,
        run_id="late-policy",
    )
    canonicalize_from_raw_logs(
        raw_log_path=late_raw,
        output_dir=tmp_path / "out_late",
        timeframe_ms=60_000,
        run_id="late-policy",
    )

    assert (tmp_path / "out_base" / "canonical_ohlcv.jsonl").read_bytes() == (
        tmp_path / "out_late" / "canonical_ohlcv.jsonl"
    ).read_bytes()
    revision_status = json.loads(
        (tmp_path / "out_late" / "revision_status.json").read_text(encoding="utf-8")
    )
    assert revision_status["status"] == "REVISION_CANDIDATE"
    assert revision_status["reason_code"] == "late_data"
    assert revision_status["late_event_count"] == 1


def test_duplicate_seq_same_hash_idempotent(tmp_path: Path) -> None:
    raw_log = tmp_path / "raw_dup_same" / "events.jsonl"
    payload = _payload_bytes(1_700_000_000_000, "100", "1")
    row1 = _raw_record(
        ingest_seq=1,
        event_ts_ms=1_700_000_000_000,
        received_at_ms=1_700_000_000_100,
        payload_bytes=payload,
    )
    row2 = _raw_record(
        ingest_seq=1,
        event_ts_ms=1_700_000_000_000,
        received_at_ms=1_700_000_000_200,
        payload_bytes=payload,
    )
    _write_raw_jsonl(raw_log, [row1, row2])

    result = canonicalize_from_raw_logs(
        raw_log_path=raw_log,
        output_dir=tmp_path / "out_dup_same",
        timeframe_ms=60_000,
        run_id="dup-same",
    )
    assert result.fail_closed is False

    gap_status = json.loads(
        (tmp_path / "out_dup_same" / "gap_status.json").read_text(encoding="utf-8")
    )
    assert gap_status["idempotent_duplicate_count"] == 1
    assert not gap_status["duplicate_conflicts"]


def test_duplicate_seq_diff_hash_fail_closed(tmp_path: Path) -> None:
    raw_log = tmp_path / "raw_dup_conflict" / "events.jsonl"
    row1 = _raw_record(
        ingest_seq=1,
        event_ts_ms=1_700_000_000_000,
        received_at_ms=1_700_000_000_100,
        payload_bytes=_payload_bytes(1_700_000_000_000, "100", "1"),
    )
    row2 = _raw_record(
        ingest_seq=1,
        event_ts_ms=1_700_000_000_000,
        received_at_ms=1_700_000_000_200,
        payload_bytes=_payload_bytes(1_700_000_000_000, "999", "1"),
    )
    _write_raw_jsonl(raw_log, [row1, row2])

    with pytest.raises(FailClosedError) as exc:
        canonicalize_from_raw_logs(
            raw_log_path=raw_log,
            output_dir=tmp_path / "out_dup_conflict",
            timeframe_ms=60_000,
            run_id="dup-conflict",
        )

    assert exc.value.result.fail_closed is True
    gap_status = json.loads(
        (tmp_path / "out_dup_conflict" / "gap_status.json").read_text(encoding="utf-8")
    )
    assert gap_status["status"] == "GAP_UNRESOLVED"
    assert gap_status["duplicate_conflicts"]
    assert gap_status["reason"] == "duplicate_ingest_seq_conflict"


def test_manifest_contains_repro_fields(tmp_path: Path) -> None:
    raw_log = tmp_path / "raw_manifest" / "events.jsonl"
    writer = RawCaptureWriter(raw_log)
    writer.append(
        exchange_id="binance",
        market="BTCUSDT",
        transport="ws",
        source="ws_live",
        feed_channel="trades",
        received_at_ms=1_700_000_000_100,
        exchange_event_ts_ms=1_700_000_000_000,
        payload_raw_bytes=_payload_bytes(1_700_000_000_000, "100", "1"),
    )

    canonicalize_from_raw_logs(
        raw_log_path=raw_log,
        output_dir=tmp_path / "out_manifest",
        timeframe_ms=60_000,
        run_id="manifest",
    )
    manifest = json.loads((tmp_path / "out_manifest" / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["schema_version"] == "s1.manifest.v2"
    assert manifest["raw_schema_version"] == "s1.raw.capture.v2"
    assert manifest["canonical_schema_version"] == "s1.canonical.ohlcv.v1"
    assert "record_counts" in manifest
    assert "artifact_meta" in manifest
    assert "code_version" in manifest
    assert manifest["source_rule"] == "raw_log_only"


def test_equal_timestamps_deterministic_tiebreak(tmp_path: Path) -> None:
    raw_log = tmp_path / "raw_tiebreak" / "events.jsonl"
    writer = RawCaptureWriter(raw_log)

    ts_ms = 1_700_000_000_000
    writer.append(
        exchange_id="binance",
        market="BTCUSDT",
        transport="ws",
        source="ws_live",
        feed_channel="trades",
        received_at_ms=ts_ms + 100,
        exchange_event_ts_ms=ts_ms,
        payload_raw_bytes=_payload_bytes(ts_ms, "100", "1"),
    )
    writer.append(
        exchange_id="binance",
        market="BTCUSDT",
        transport="ws",
        source="ws_live",
        feed_channel="trades",
        received_at_ms=ts_ms + 200,
        exchange_event_ts_ms=ts_ms,
        payload_raw_bytes=_payload_bytes(ts_ms, "101", "1"),
    )

    canonicalize_from_raw_logs(
        raw_log_path=raw_log,
        output_dir=tmp_path / "out_tiebreak",
        timeframe_ms=60_000,
        run_id="tiebreak",
    )

    bars = [
        json.loads(line)
        for line in (tmp_path / "out_tiebreak" / "canonical_ohlcv.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(bars) == 1
    assert bars[0]["open"] == "100"
    assert bars[0]["close"] == "101"
