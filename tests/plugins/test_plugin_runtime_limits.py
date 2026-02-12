import math
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
    expected_cpu = max(1, int(math.ceil(validation_module.RUNTIME_TIMEOUT_SECONDS)) + 1)
    assert cpu_calls[0][1] == (expected_cpu, expected_cpu)
    if hasattr(resource, "RLIMIT_AS"):
        as_calls = [call for call in calls if call[0] == resource.RLIMIT_AS]
        assert as_calls
        assert as_calls[0][1] == (512 * 1024 * 1024, 512 * 1024 * 1024)
