"""Shared settings and helpers for landing-site metric evaluation."""

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from math import isclose

MAX_EPHEMERIS_SAMPLES = 3000
DEFAULT_FOOTPRINT_RADIUS_M = 250.0


def availability_metrics(
    available: Sequence[bool],
    step_hours: float,
) -> tuple[float, float] | None:
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


def validate_interval(
    start_time: datetime,
    end_time: datetime,
    step_minutes: int,
) -> tuple[datetime, datetime, int]:
    """Validate a mission interval and return UTC bounds and sample count."""
    if not isinstance(start_time, datetime) or not isinstance(end_time, datetime):
        raise ValueError("mission_start and mission_end must be datetime values")

    if start_time.utcoffset() is None or end_time.utcoffset() is None:
        raise ValueError("mission_start and mission_end must include a timezone")

    if not isinstance(step_minutes, int) or isinstance(step_minutes, bool):
        raise ValueError("step_minutes must be a positive integer")

    if not 1 <= step_minutes <= 1440:
        raise ValueError("step_minutes must be between 1 and 1440")

    start = start_time.astimezone(timezone.utc)
    end = end_time.astimezone(timezone.utc)
    duration_seconds = (end - start).total_seconds()
    step_seconds = step_minutes * 60

    if duration_seconds <= 0:
        raise ValueError("mission_end must be later than mission_start")

    count = round(duration_seconds / step_seconds)
    if not isclose(
        duration_seconds,
        count * step_seconds,
        rel_tol=0.0,
        abs_tol=1e-6,
    ):
        raise ValueError(
            "The mission interval must be divisible by step_minutes"
        )

    if count < 1 or count > MAX_EPHEMERIS_SAMPLES:
        raise ValueError(
            "The mission interval must contain between 1 and "
            f"{MAX_EPHEMERIS_SAMPLES} samples"
        )

    return start, end, count


def state_windows(
    states: Sequence[bool],
    start: datetime,
    step_minutes: int,
    target: bool,
) -> list[dict[str, str]]:
    """Group consecutive Boolean states into ISO-8601 time windows."""
    windows = []
    opened_at = None

    for index, state in enumerate([*states, None]):
        boundary = start + timedelta(minutes=index * step_minutes)

        if state is target and opened_at is None:
            opened_at = boundary
        elif state is not target and opened_at is not None:
            windows.append(
                {
                    "start": opened_at.isoformat(),
                    "end": boundary.isoformat(),
                }
            )
            opened_at = None

    return windows
