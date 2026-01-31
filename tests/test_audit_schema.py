"""Tests for audit schema helpers."""

from __future__ import annotations

from audit.schema import canonical_json, sha256_hex


def test_canonical_json_deterministic() -> None:
    payload_a = {"b": 2, "a": 1, "c": {"z": 3, "y": 2}}
    payload_b = {"c": {"y": 2, "z": 3}, "a": 1, "b": 2}
    assert canonical_json(payload_a) == canonical_json(payload_b)
    assert canonical_json(payload_a) == '{"a":1,"b":2,"c":{"y":2,"z":3}}'


def test_sha256_hex_stable() -> None:
    value = "stable"
    assert sha256_hex(value) == sha256_hex(value)
