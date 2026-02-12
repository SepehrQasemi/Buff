import os

import pytest

from src.plugins import validation as validation_module


@pytest.mark.skipif(os.name != "posix", reason="resource limits only apply on posix")
def test_apply_resource_limits_invokes_setrlimit(monkeypatch):
    import resource

    calls = []

    def fake_setrlimit(kind, limits):
        calls.append((kind, limits))

    monkeypatch.setattr(resource, "setrlimit", fake_setrlimit)

    validation_module._apply_resource_limits()

    assert any(call[0] == resource.RLIMIT_CPU for call in calls)
    if hasattr(resource, "RLIMIT_AS"):
        assert any(call[0] == resource.RLIMIT_AS for call in calls)
