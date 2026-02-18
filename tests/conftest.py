from __future__ import annotations

import sys
from pathlib import Path

import pytest


def _add_src_to_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_path = repo_root / "src"
    if src_path.exists():
        src_str = str(src_path)
        if src_str not in sys.path:
            sys.path.insert(0, src_str)


_add_src_to_path()


@pytest.fixture(autouse=True)
def _default_user_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUFF_DEFAULT_USER", "test-user")
    monkeypatch.delenv("BUFF_USER_HMAC_SECRET", raising=False)
