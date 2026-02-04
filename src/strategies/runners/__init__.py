"""Strategy runners."""

from .mean_revert_v1 import MEAN_REVERT_V1_SPEC, mean_revert_v1_runner
from .trend_follow_v1 import TREND_FOLLOW_V1_SPEC, trend_follow_v1_runner

__all__ = [
    "MEAN_REVERT_V1_SPEC",
    "mean_revert_v1_runner",
    "TREND_FOLLOW_V1_SPEC",
    "trend_follow_v1_runner",
]
