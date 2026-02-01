from __future__ import annotations

import math

import pytest

from audit.canonical_json import canonical_json


def test_canonical_rejects_nan() -> None:
    payload = {"a": [1.0, math.nan]}
    with pytest.raises(ValueError, match=r"\$\.a\[1\]"):
        canonical_json(payload)


def test_canonical_rejects_inf() -> None:
    payload = {"a": {"b": math.inf}}
    with pytest.raises(ValueError, match=r"\$\.a\.b"):
        canonical_json(payload)


def test_canonical_normalizes_negative_zero() -> None:
    payload = {"x": -0.0}
    assert canonical_json(payload) == '{"x":0.00000000}'


def test_int_and_float_policy_is_consistent() -> None:
    payload = {"i": 1, "f": 1.0}
    assert canonical_json(payload) == '{"f":1.00000000,"i":1}'
