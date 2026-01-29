from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SandboxPolicy:
    allowed_imports: set[str] = field(
        default_factory=lambda: {"numpy", "pandas", "math", "typing", "dataclasses"}
    )
    forbidden_imports: set[str] = field(
        default_factory=lambda: {"os", "sys", "subprocess", "socket", "requests", "pathlib"}
    )


class SandboxViolation(ValueError):
    pass


def validate_code(code: str, policy: SandboxPolicy | None = None) -> None:
    policy = policy or SandboxPolicy()
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name.split(".")[0]
                _validate_module(module, policy)
        if isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            module = node.module.split(".")[0]
            _validate_module(module, policy)


def _validate_module(module: str, policy: SandboxPolicy) -> None:
    if module in policy.forbidden_imports:
        raise SandboxViolation(f"forbidden_import:{module}")
    if module not in policy.allowed_imports:
        raise SandboxViolation(f"not_allowed_import:{module}")
