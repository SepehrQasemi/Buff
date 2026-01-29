from __future__ import annotations

import multiprocessing as mp
from typing import Any

from .policy import SandboxPolicy, SandboxViolation, validate_code


def run_sandboxed(
    code: str,
    entrypoint: str,
    *args: Any,
    timeout_seconds: float = 1.0,
    policy: SandboxPolicy | None = None,
    **kwargs: Any,
) -> Any:
    validate_code(code, policy=policy)
    ctx = mp.get_context("spawn")
    queue: mp.Queue[Any] = ctx.Queue()
    process = ctx.Process(
        target=_sandbox_worker,
        args=(code, entrypoint, args, kwargs, queue),
    )
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join()
        raise TimeoutError("sandbox_timeout")

    if queue.empty():
        raise SandboxViolation("sandbox_no_result")
    result = queue.get()
    if isinstance(result, Exception):
        raise result
    return result


def _sandbox_worker(
    code: str,
    entrypoint: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    queue: mp.Queue[Any],
) -> None:
    safe_builtins = {
        "abs": abs,
        "min": min,
        "max": max,
        "sum": sum,
        "len": len,
        "range": range,
        "float": float,
        "int": int,
        "str": str,
        "dict": dict,
        "list": list,
        "set": set,
        "tuple": tuple,
        "enumerate": enumerate,
        "__import__": __import__,
    }
    globals_dict: dict[str, Any] = {"__builtins__": safe_builtins}
    locals_dict = globals_dict
    try:
        exec(code, globals_dict, locals_dict)
        func = locals_dict.get(entrypoint) or globals_dict.get(entrypoint)
        if func is None:
            raise SandboxViolation("entrypoint_not_found")
        result = func(*args, **kwargs)
        queue.put(result)
    except Exception as exc:  # pragma: no cover - used in subprocess
        queue.put(exc)
