from __future__ import annotations

import pytest

from apps.api.phase6.paths import validate_run_id, validate_user_id


@pytest.mark.parametrize(
    "value",
    [
        "../escape",
        "..%2fescape",
        "%2e%2e",
        ".",
        "..",
        "user/child",
        r"user\\child",
        "．",
    ],
)
def test_user_id_traversal_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        validate_user_id(value)


@pytest.mark.parametrize(
    "value",
    [
        "../run",
        "..%2f",
        "%2e%2e",
        ".",
        "..",
        "run/name",
        r"run\\name",
    ],
)
def test_run_id_traversal_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        validate_run_id(value)
