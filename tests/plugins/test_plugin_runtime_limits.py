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

    cpu_calls = [call for call in calls if call[0] == resource.RLIMIT_CPU]
    assert cpu_calls
    cpu_soft, cpu_hard = cpu_calls[0][1]
    assert cpu_soft == cpu_hard
    assert isinstance(cpu_soft, int)
    assert cpu_soft >= 1
    if hasattr(resource, "RLIMIT_AS"):
        as_calls = [call for call in calls if call[0] == resource.RLIMIT_AS]
        assert as_calls
        as_soft, as_hard = as_calls[0][1]
        assert as_soft == as_hard
        assert isinstance(as_soft, int)
        assert as_soft > 0
        if hasattr(resource, "RLIM_INFINITY"):
            assert as_soft != resource.RLIM_INFINITY
