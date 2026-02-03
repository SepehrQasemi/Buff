Fixture Integrity
- `tests/fixtures/ohlcv/ohlcv_1m_fixture.parquet` is treated as immutable.
- A SHA256 guard test asserts the exact bytes; do not regenerate or modify the file.
