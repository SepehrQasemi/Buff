from __future__ import annotations

from typing import Any


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--cache-dir",
        action="store",
        default=None,
        help="Override pytest cache directory.",
    )


def pytest_configure(config: Any) -> None:
    cache_dir = config.getoption("--cache-dir")
    if cache_dir:
        config._inicache["cache_dir"] = cache_dir
