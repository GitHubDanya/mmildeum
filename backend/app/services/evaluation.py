"""Shared settings and helpers for landing-site metric evaluation."""

from collections.abc import Sequence

EPHEMERIS_START = "2026-11-01"
EPHEMERIS_STOP = "2026-11-30 12:44"
EPHEMERIS_STEP = "2 h"
EPHEMERIS_STEP_HOURS = 2.0
DEFAULT_FOOTPRINT_RADIUS_M = 250.0


def availability_metrics(available: Sequence[bool], step_hours: float = EPHEMERIS_STEP_HOURS,) -> tuple[float, float] | None:
    """Return available-time fraction and longest unavailable run.

    Each Boolean sample represents one regular interval of ``step_hours``.
    The interval is intentionally not treated as cyclic: outages at the
    beginning and end of the configured evaluation period remain separate.
    """
    if not available:
        return None

    longest_run = 0
    current_run = 0

    for is_available in available:
        if is_available:
            current_run = 0
        else:
            current_run += 1
            longest_run = max(longest_run, current_run)

    fraction = sum(available) / len(available)
    return fraction, longest_run * step_hours
