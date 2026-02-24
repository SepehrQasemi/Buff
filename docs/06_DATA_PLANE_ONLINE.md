# 06_DATA_PLANE_ONLINE

## Purpose
Define the mandatory online data plane for Buff's futures R&D lifecycle.

## Scope
In scope:
- Online market data collection
- Immutable raw event capture
- Canonical OHLCV construction
- Deterministic replay from raw data

Out of scope:
- Strategy decisions
- Execution routing
- Order placement

## Feed Adapter Concept
A Feed Adapter is the single market-ingest abstraction with:
- WebSocket primary stream for low-latency event flow
- REST fallback for continuity and gap backfill
- Deterministic sequencing and clock normalization

Required adapter behaviors:
- Normalize source event timestamps to UTC epoch milliseconds
- Emit monotonic ingest sequence IDs per stream
- Fail closed on malformed, duplicate-with-conflict, or out-of-contract payloads

## Raw Immutable Event Log Schema
Each captured event must be append-only and immutable.

Minimum schema fields:
- `stream_id`: source stream identity
- `ingest_seq`: strictly increasing ingest sequence number
- `event_ts_exchange_ms`: exchange-provided event timestamp (ms)
- `event_ts_ingest_ms`: local ingest timestamp (ms)
- `symbol`: canonical instrument key
- `channel`: feed channel (trade/book/ticker/mark/etc.)
- `payload_raw`: original payload bytes or canonicalized payload string
- `payload_sha256`: digest of `payload_raw`
- `source`: `ws` or `rest_backfill`
- `schema_version`: raw event schema version

## Canonical OHLCV Construction
Canonical OHLCV must be derived only from raw event logs.

Construction rules:
- Time bucket key: UTC epoch boundary by configured timeframe
- Deterministic ordering: `(event_ts_exchange_ms, ingest_seq)`
- Aggregation:
  - open = first trade price in bucket
  - high = max trade price in bucket
  - low = min trade price in bucket
  - close = last trade price in bucket
  - volume = sum of trade size
- Every canonical bar must carry provenance pointers to source raw ranges/digests

## Gap Policy
- Detect missing intervals against expected bucket schedule.
- Attempt REST backfill for missing intervals.
- If gap remains unresolved after bounded retries, mark interval status as `GAP_UNRESOLVED`.
- Fail closed for downstream pipelines that require gap-free canonical bars.

## Late Data Policy
Late data is any event that arrives after its bucket has been sealed.

Policy:
- Late events are recorded in raw logs without mutation.
- Canonical layer emits explicit late-data revision candidate metadata.
- No silent bar mutation is allowed.

## Revision Policy
Canonical outputs are revisioned, never silently overwritten.

Rules:
- Revision creates a new canonical artifact version with deterministic diff metadata.
- Prior versions remain addressable.
- Each revision includes reason code (`late_data`, `source_correction`, `rebuild`, etc.).

## Replay Requirement
The data plane must guarantee reproducibility:
- Input: raw immutable event logs + canonicalization config
- Output: byte-stable canonical OHLCV artifacts and digests

Replay acceptance condition:
- Replayed canonical outputs must match stored digests for the same raw input set and config version.

## Non-Goal
No execution authority exists in this layer.
This layer never decides trades and never routes orders.
