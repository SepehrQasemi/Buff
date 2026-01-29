"""Paper runner for smoke testing decision pipeline."""

from .long_run import LongRunConfig, run_long_paper
from .paper_runner import PaperRunConfig, run_paper_smoke

__all__ = ["LongRunConfig", "PaperRunConfig", "run_long_paper", "run_paper_smoke"]
