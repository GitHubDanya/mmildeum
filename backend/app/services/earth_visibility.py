"""Terrain-aware Earth visibility over a lunar mission interval."""

import csv
import io
import re
from datetime import datetime, timedelta
from math import isfinite
from typing import Any, Mapping

import requests

from app.services.evaluation import (
    availability_metrics,
    state_windows,
    validate_interval,
)
from app.services.terrain_horizon import get_terrain_horizon, is_body_visible


HORIZONS_API_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"


class EarthVisibilityDataUnavailable(RuntimeError):
    """Signal that usable terrestrial ephemeris data could not be obtained."""


def _horizons_positions(
    lat: float,
    lon: float,
    start: datetime,
    step_minutes: int,
    count: int,
) -> list[tuple[float, float]]:
    """Fetch Earth azimuth and elevation samples from JPL Horizons."""
    step = timedelta(minutes=step_minutes)
    first = start + step / 2
    end = start + step * count

    params = {
        "format": "json",
        "COMMAND": "'399'",
        "MAKE_EPHEM": "'YES'",
        "OBJ_DATA": "'NO'",
        "EPHEM_TYPE": "'OBSERVER'",
        "CENTER": "'coord@301'",
        "COORD_TYPE": "'GEODETIC'",
        "SITE_COORD": f"'{lon % 360},{lat},0'",
        "START_TIME": f"'{first.strftime('%Y-%m-%d %H:%M:%S')}'",
        "STOP_TIME": f"'{end.strftime('%Y-%m-%d %H:%M:%S')}'",
        "STEP_SIZE": f"'{step_minutes} m'",
        "QUANTITIES": "'4'",
        "CSV_FORMAT": "'YES'",
        "CAL_FORMAT": "'JD'",
        "TIME_TYPE": "'UT'",
        "APPARENT": "'AIRLESS'",
        "ANG_FORMAT": "'DEG'",
    }

    try:
        response = requests.get(
            HORIZONS_API_URL,
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise EarthVisibilityDataUnavailable(
            "JPL Horizons request failed"
        ) from exc

    if isinstance(data, dict) and data.get("error"):
        error_message = str(data["error"])[:300]
        raise EarthVisibilityDataUnavailable(
            f"JPL Horizons rejected the request: {error_message}"
        )

    raw = data.get("result") if isinstance(data, dict) else None
    if not isinstance(raw, str):
        raise EarthVisibilityDataUnavailable(
            "JPL Horizons response has no ephemeris"
        )

    match = re.search(
        r"^[ \t]*\$\$SOE[ \t]*\r?\n(.*?)^[ \t]*\$\$EOE[ \t]*$",
        raw,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise EarthVisibilityDataUnavailable(
            "JPL Horizons returned no ephemeris table"
        )

    rows = [
        row
        for row in csv.reader(io.StringIO(match.group(1)))
        if any(cell.strip() for cell in row)
    ]
    if len(rows) != count:
        raise EarthVisibilityDataUnavailable(
            f"JPL Horizons returned {len(rows)} samples, expected {count}"
        )

    positions = []
    for index, row in enumerate(rows):
        fields = [cell.strip() for cell in row if cell.strip()]
        try:
            julian_day = float(fields[0])
            azimuth = float(fields[-2])
            elevation = float(fields[-1])
        except (IndexError, ValueError) as exc:
            raise EarthVisibilityDataUnavailable(
                "Invalid terrestrial ephemeris row"
            ) from exc

        midpoint = first + step * index
        expected_jd = midpoint.timestamp() / 86400.0 + 2440587.5
        if (
            not all(
                isfinite(value)
                for value in (julian_day, azimuth, elevation)
            )
            or abs(julian_day - expected_jd) > 2.0 / 86400.0
            or not (0 <= azimuth <= 360 and -90 <= elevation <= 90)
        ):
            raise EarthVisibilityDataUnavailable(
                "Inconsistent terrestrial ephemeris data"
            )

        positions.append((azimuth, elevation))

    return positions


def get_earth_visibility_window(
    lat: float,
    lon: float,
    start_time: datetime,
    end_time: datetime,
    *,
    step_minutes: int = 60,
    horizon_data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate terrain-aware Earth visibility for a mission interval."""
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

    start, end, count = validate_interval(
        start_time,
        end_time,
        step_minutes,
    )
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
    states = [
        is_body_visible(horizon, azimuth, elevation)
        for azimuth, elevation in positions
    ]

    result = {
        "latitude": lat,
        "longitude": lon,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "step_minutes": step_minutes,
        "sample_count": count,
        "unknown_samples": sum(state is None for state in states),
        "windows": None,
        "earth_visibility_fraction": None,
        "longest_earth_blackout_hours": None,
        "data_quality": "insufficient_data",
        "horizon_data_quality": horizon.get("data_quality"),
    }

    if result["unknown_samples"]:
        return result

    visible_states = [bool(state) for state in states]
    metrics = availability_metrics(
        visible_states,
        step_minutes / 60.0,
    )
    if metrics is None:
        return result

    visibility_fraction, longest_blackout = metrics
    result.update(
        windows=state_windows(
            visible_states,
            start,
            step_minutes,
            True,
        ),
        earth_visibility_fraction=visibility_fraction,
        longest_earth_blackout_hours=longest_blackout,
        data_quality="complete_within_radius",
    )
    return result
