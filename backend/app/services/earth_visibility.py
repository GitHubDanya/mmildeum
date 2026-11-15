import re
import requests
from .evaluation import (
    EPHEMERIS_START,
    EPHEMERIS_STEP,
    EPHEMERIS_STEP_HOURS,
    EPHEMERIS_STOP,
    availability_metrics,
)
from .terrain_horizon import get_terrain_horizon, is_body_visible

HORIZONS_API_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"


def get_earth_visibility_window(lat: float, lon: float) -> dict | None:
    """Calculate time windows when Earth is visible above local terrain from a lunar coordinate."""
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 360):
        return None

    horizon_data = get_terrain_horizon(lat, lon)
    match = get_horizons_visibility_windows(lat, lon)
    if match is None:
        return {
            "latitude": lat,
            "longitude": lon,
            "windows": [],
            "earth_visibility_fraction": None,
            "longest_earth_blackout_hours": None,
        }

    lines = match.group(1).strip().splitlines()

    terrain_map = {}
    for item in horizon_data["profile"]:
        if isinstance(item, dict):
            azim = item.get("azimuth_deg")
            angle = item.get("horizon_elevation_deg")
        else:
            azim, angle = item[0], item[1]
        terrain_map[azim] = angle

    visible_windows = []
    current_start = None
    last_timestamp = None
    visibility_samples = []

    for line in lines:
        parts = [p.strip() for p in line.split(",") if p.strip()]
        if len(parts) < 3:
            continue

        try:
            elevation = float(parts[-1])
            azimuth = float(parts[-2])
            timestamp = parts[0]
        except ValueError:
            continue

        last_timestamp = timestamp
        visible = is_body_visible(horizon_data, azimuth, elevation)
        if visible is None:
            visible = elevation > get_blocking_angle(azimuth, terrain_map)

        visibility_samples.append(visible)

        if visible and current_start is None:
            current_start = timestamp
        elif not visible and current_start is not None:
            visible_windows.append({
                "start": current_start,
                "end": timestamp,
            })
            current_start = None

    # Close any window still open at the end of the ephemeris period
    if current_start is not None and last_timestamp is not None:
        visible_windows.append({
            "start": current_start,
            "end": last_timestamp,
        })

    metrics = availability_metrics(visibility_samples)
    if metrics is None:
        visibility_fraction = None
        longest_blackout_hours = None
    else:
        visibility_fraction, longest_blackout_hours = metrics

    return {
        "latitude": lat,
        "longitude": lon,
        "windows": visible_windows,
        "earth_visibility_fraction": visibility_fraction,
        "longest_earth_blackout_hours": longest_blackout_hours,
        "sample_count": len(visibility_samples),
        "time_step_hours": EPHEMERIS_STEP_HOURS,
        "period_start": EPHEMERIS_START,
        "period_stop": EPHEMERIS_STOP,
    }


def get_blocking_angle(target_az: float, terrain_map: dict) -> float:
    """Return the minimum elevation angle required for visibility at target_az."""
    if not terrain_map:
        return 0.0

    normalized_az = target_az % 360.0
    closest_az = min(
        terrain_map.keys(),
        key=lambda a: min(abs(a - normalized_az), 360.0 - abs(a - normalized_az)),
    )
    blocking_angle = terrain_map[closest_az]
    return blocking_angle if blocking_angle is not None else 0.0


def get_horizons_visibility_windows(lat: float, lon: float):
    """Fetch apparent azimuth and elevation ephemeris from JPL Horizons API."""
    params = {
        "format": "json",
        "COMMAND": "'399'",  # 399 = Earth
        "EPHEM_TYPE": "'OBSERVER'",
        "CENTER": "'coord@301'",  # 301 = The Moon
        "SITE_COORD": f"'{lon},{lat},0'",
        "START_TIME": f"'{EPHEMERIS_START}'",
        "STOP_TIME": f"'{EPHEMERIS_STOP}'",
        "STEP_SIZE": f"'{EPHEMERIS_STEP}'",
        "QUANTITIES": "'4'",  # 4 = Apparent Azimuth & Elevation
        "CSV_FORMAT": "'YES'",
    }

    try:
        response = requests.get(HORIZONS_API_URL, params=params, timeout=15)
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None

    raw_resp = response.json().get("result", "")
    return re.search(r"\$\$SOE\s*(.*?)\s*\$\$EOE", raw_resp, re.DOTALL)
