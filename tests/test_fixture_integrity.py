from __future__ import annotations

from hashlib import sha256
from pathlib import Path


def test_ohlcv_fixture_sha256_guard() -> None:
    path = Path("tests/fixtures/ohlcv/ohlcv_1m_fixture.parquet")
    digest = sha256(path.read_bytes()).hexdigest()
    assert digest == "86714e19b94093447c4bc2f2a0a2f768db366805992b85afa5cfce79e797ebcf"
