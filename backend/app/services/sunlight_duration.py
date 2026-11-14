"""Terrain-aware sunlight duration over a chosen lunar mission interval."""

import csv
import io
import re
from datetime import datetime, timedelta, timezone
from math import isclose, isfinite
from typing import Any, Mapping

import requests

from app.services.terrain_horizon import get_terrain_horizon, is_body_visible


HORIZONS_API_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
MAX_SAMPLES = 3000


class SunlightDataUnavailable(RuntimeError):
    """Signal that usable solar ephemeris data could not be obtained."""


def _validate_interval(
    start_time: datetime,
    end_time: datetime,
    step_minutes: int,
) -> tuple[datetime, datetime, int]:
    """Validate the mission interval and sampling frequency.

    Args:
        start_time: Requested interval start with a timezone.
        end_time: Requested interval end with a timezone.
        step_minutes: Interval width in minutes.

    Returns:
        Normalized UTC start, UTC end, and interval count.
    """
    if not isinstance(start_time, datetime) or not isinstance(end_time, datetime):
        raise ValueError("start_time and end_time must be datetime values")

    if start_time.tzinfo is None or end_time.tzinfo is None:
        raise ValueError("start_time and end_time must include a timezone")

    if not isinstance(step_minutes, int) or isinstance(step_minutes, bool):
        raise ValueError("step_minutes must be a positive integer")

    if not 1 <= step_minutes <= 1440:
        raise ValueError("step_minutes must be between 1 and 1440")

    start = start_time.astimezone(timezone.utc)
    end = end_time.astimezone(timezone.utc)
    duration_seconds = (end - start).total_seconds()
    step_seconds = step_minutes * 60

    if duration_seconds <= 0:
        raise ValueError("end_time must be later than start_time")

    count = round(duration_seconds / step_seconds)

    if not isclose(duration_seconds, count * step_seconds, abs_tol=1e-6):
        raise ValueError(
            "The interval duration must be divisible by step_minutes"
        )

    if count < 1 or count > MAX_SAMPLES:
        raise ValueError(
            f"The interval must contain between 1 and {MAX_SAMPLES} samples"
        )

    return start, end, count


def _horizons_positions(
    lat: float,
    lon: float,
    start: datetime,
    step_minutes: int,
    count: int,
) -> list[tuple[float, float]]:
    """Fetch solar azimuth and elevation from JPL Horizons.

    Args:
        lat: Selenographic latitude.
        lon: East-positive longitude.
        start: Mission start in UTC.
        step_minutes: Size of each interval.
        count: Number of midpoints to query.

    Returns:
        Angle pairs (azimuth, elevation), one per expected midpoint.
    """
    step = timedelta(minutes=step_minutes)
    first = start + step / 2
    end = start + step * count

    params = dict(
        format="json",
        COMMAND="'10'",
        MAKE_EPHEM="'YES'",
        OBJ_DATA="'NO'",
        EPHEM_TYPE="'OBSERVER'",
        CENTER="'coord@301'",
        COORD_TYPE="'GEODETIC'",
        SITE_COORD=f"'{lon % 360},{lat},0'",
        START_TIME=f"'{first.strftime('%Y-%m-%d %H:%M:%S')}'",
        STOP_TIME=f"'{end.strftime('%Y-%m-%d %H:%M:%S')}'",
        STEP_SIZE=f"'{step_minutes} m'",
        QUANTITIES="'4'",
        CSV_FORMAT="'YES'",
        CAL_FORMAT="'JD'",
        TIME_TYPE="'UT'",
        APPARENT="'AIRLESS'",
        ANG_FORMAT="'DEG'",
    )

    try:
        response = requests.get(
            HORIZONS_API_URL,
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise SunlightDataUnavailable(
            "JPL Horizons request failed"
        ) from exc

    raw = data.get("result") if isinstance(data, dict) else None

    if not isinstance(raw, str):
        raise SunlightDataUnavailable(
            "JPL Horizons response has no ephemeris"
        )

    match = re.search(
        r"\$\$SOE\s*(.*?)\s*\$\$EOE",
        raw,
        re.DOTALL,
    )

    if match is None:
        raise SunlightDataUnavailable(
            "JPL Horizons returned no ephemeris table"
        )

    rows = [
        row for row in csv.reader(io.StringIO(match.group(1)))
        if any(cell.strip() for cell in row)
    ]

    if len(rows) != count:
        raise SunlightDataUnavailable(
            f"JPL Horizons returned {len(rows)} samples, expected {count}"
        )

    positions = []

    for index, row in enumerate(rows):
        fields = [
            cell.strip()
            for cell in row
            if cell.strip()
        ]

        try:
            julian_day = float(fields[0])
            azimuth = float(fields[-2])
            elevation = float(fields[-1])
        except (IndexError, ValueError) as exc:
            raise SunlightDataUnavailable(
                "Invalid solar ephemeris row"
            ) from exc

        midpoint = first + step * index
        expected_jd = (
            midpoint.timestamp() / 86400.0
            + 2440587.5
        )

        if (
            not all(
                isfinite(value)
                for value in (julian_day, azimuth, elevation)
            )
            or abs(julian_day - expected_jd) > 2.0 / 86400.0
            or not (0 <= azimuth <= 360 and -90 <= elevation <= 90)
        ):
            raise SunlightDataUnavailable(
                "Inconsistent solar ephemeris data"
            )

        positions.append((azimuth, elevation))

    return positions


def _sunlight_windows(
    states: list[bool],
    start: datetime,
    step_minutes: int,
    target: bool,
) -> list[dict[str, str]]:
    """Group consecutive visibility states into time windows.

    Args:
        states: Complete list of binary sunlight visibility samples.
        start: Mission start in UTC.
        step_minutes: Length of an individual interval.
        target: True for illuminated windows, False for dark windows.

    Returns:
        Ordered start/end ISO-8601 pairs representing estimated windows.
    """
    windows = []
    opened_at = None

    for index, state in enumerate([*states, None]):
        boundary = start + timedelta(
            minutes=index * step_minutes
        )

        if state is target and opened_at is None:
            opened_at = boundary

        elif state is not target and opened_at is not None:
            windows.append(
                dict(
                    start=opened_at.isoformat(),
                    end=boundary.isoformat(),
                )
            )
            opened_at = None

    return windows


def get_average_duration_of_sunlight(
    lat: float,
    lon: float,
    start_time: datetime,
    end_time: datetime,
    *,
    step_minutes: int = 60,
    horizon_data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate terrain-aware sunlight duration for a chosen mission interval.

    Args:
        lat: Lunar latitude, in degrees (-90 through 90).
        lon: East-positive lunar longitude, in degrees (-180 through 360).
        start_time: Inclusive, timezone-aware start of the mission interval.
        end_time: Exclusive, timezone-aware end of the interval.
        step_minutes: Length of each equal interval, in whole minutes.
        horizon_data: Optional previously computed local terrain horizon.

    Returns:
        Sunlight fraction, percentage, total and average hours,
        longest darkness, and estimated sunlight windows.
        Missing terrain coverage produces null metrics.

    Raises:
        ValueError: For invalid inputs or unsupported intervals.
        SunlightDataUnavailable: When JPL Horizons data is unusable.
        TerrainDataUnavailable: When the terrain horizon is unavailable.
    """
    if (
        isinstance(lat, bool)
        or isinstance(lon, bool)
        or not isinstance(lat, (int, float))
        or not isinstance(lon, (int, float))
        or not isfinite(lat)
        or not isfinite(lon)
        or not -90 <= lat <= 90
        or not -180 <= lon <= 360
    ):
        raise ValueError(
            "Latitude must be in [-90, 90] "
            "and longitude in [-180, 360]"
        )

    start, end, count = _validate_interval(
        start_time,
        end_time,
        step_minutes,
    )

    # Reuse a precomputed horizon or calculate it only once.
    horizon = (
        horizon_data
        if horizon_data is not None
        else get_terrain_horizon(lat, lon)
    )

    positions = _horizons_positions(
        lat,
        lon,
        start,
        step_minutes,
        count,
    )

    # Compare each sampled Sun position against local terrain.
    states = [
        is_body_visible(horizon, azimuth, elevation)
        for azimuth, elevation in positions
    ]

    result = dict(
        latitude=lat,
        longitude=lon,
        start_time=start.isoformat(),
        end_time=end.isoformat(),
        step_minutes=step_minutes,
        sample_count=count,
        unknown_samples=sum(state is None for state in states),
        sunlight_fraction=None,
        sunlight_percentage=None,
        total_sunlight_hours=None,
        average_sunlight_hours_per_24h=None,
        longest_darkness_hours=None,
        sunlight_windows=None,
        data_quality="insufficient_data",
        horizon_data_quality=horizon.get("data_quality"),
    )

    if result["unknown_samples"]:
        return result

    visible_states = [
        bool(state)
        for state in states
    ]

    sunlight_hours = (
        sum(visible_states) * step_minutes / 60.0
    )

    fraction = sum(visible_states) / count

    darkness_windows = _sunlight_windows(
        visible_states,
        start,
        step_minutes,
        False,
    )

    longest_darkness = max(
        (
            (
                datetime.fromisoformat(item["end"])
                - datetime.fromisoformat(item["start"])
            ).total_seconds() / 3600
            for item in darkness_windows
        ),
        default=0.0,
    )

    result.update(
        sunlight_fraction=fraction,
        sunlight_percentage=100.0 * fraction,
        total_sunlight_hours=sunlight_hours,
        average_sunlight_hours_per_24h=24.0 * fraction,
        longest_darkness_hours=longest_darkness,
        sunlight_windows=_sunlight_windows(
            visible_states,
            start,
            step_minutes,
            True,
        ),
        data_quality="complete_within_radius",
    )

    return result
