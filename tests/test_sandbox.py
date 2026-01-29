from __future__ import annotations

import pytest

from sandbox.policy import SandboxViolation, validate_code
from sandbox.runner import run_sandboxed


def test_sandbox_blocks_forbidden_import() -> None:
    code = "import os\n\n" "def foo():\n    return 1\n"
    with pytest.raises(SandboxViolation, match="forbidden_import"):
        validate_code(code)


def test_sandbox_allows_safe_code_execution() -> None:
    code = "import math\n\n" "def compute(x):\n    return math.sqrt(x)\n"
    result = run_sandboxed(code, "compute", 9.0, timeout_seconds=1.0)
    assert result == 3.0
