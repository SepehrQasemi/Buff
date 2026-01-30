from __future__ import annotations

from decision_records.digest import inputs_digest


def test_digest_deterministic_across_key_order() -> None:
    payload_a = {"b": 2, "a": 1}
    payload_b = {"a": 1, "b": 2}
    assert inputs_digest(payload_a) == inputs_digest(payload_b)
