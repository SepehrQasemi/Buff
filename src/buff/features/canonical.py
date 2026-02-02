"""Canonical serialization helpers for feature contracts."""

from __future__ import annotations

from typing import Any

from audit.canonical_json import canonical_json_bytes as _canonical_json_bytes


def canonical_json_bytes(obj: Any) -> bytes:
    """Serialize an object to deterministic canonical JSON bytes."""
    return _canonical_json_bytes(obj)


def canonical_json_str(obj: Any) -> str:
    """Serialize an object to deterministic canonical JSON string."""
    return canonical_json_bytes(obj).decode("utf-8")
