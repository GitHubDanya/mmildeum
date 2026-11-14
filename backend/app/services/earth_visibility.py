import requests
import re
from .terrain_horizon import get_terrain_horizon

HORIZONS_API_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"

def get_earth_visibility_window(lat: float, lon: float) -> dict[str, float] | None:
    """
    Function to get Longest time Earth is visible From a lunar coordinate
    :param lat: Latitude in degrees (-90 to 90)
    :type lat: float
    :param lon: Longitude in degrees (-180 to 360)
    :type lon: float
    :return: Dictionary with average Sun angle at Daytime & Full Moon Cycle, or None if no data
    :rtype: dict | None
    """
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 360):
        return None

    horizon_data = get_terrain_horizon(lat, lon)
    match = get_horizons_visibility_windows(lat, lon)

    lines = match.group(1).strip().splitlines()
    # Get Map of terrain to check Visibility later
    terrain_map = {}
    for item in horizon_data["profile"]:
        if isinstance(item, dict):
            azim = item.get("azimuth_deg")
            angle = item.get("horizon_elevation_deg")
        else:
            azim, angle = item[0], item[1]
        terrain_map[azim] = angle

    all_windows = []
    visible_windows = {}
    current_start = None
    last_timestamp = None

    for line in lines:
        parts = []
        for p in line.split(","):
            if p.strip():
                parts.append(p.strip())

        try:
            elevation = float(parts[-1])
            azimuth = float(parts[-2])
            timestamp = parts[0]
            all_windows.append((elevation, azimuth))
        except ValueError:
            continue


        # Record all time windows where earth is visible
        last_timestamp = timestamp
        is_visible = elevation > get_blocking_angle(azimuth, terrain_map)

        if is_visible and last_timestamp is None:
            current_start = timestamp

        # earth dipped behind terrain
        elif not is_visible and current_start is not None:
            visible_windows.append({
                "start": current_start,
                "end": timestamp
            })
            current_start = None
        # Last visible timestamp check
        if current_start is not None and last_timestamp is not None:
            visible_windows.append({
                "start": current_start,
                "end": last_timestamp
            })

    return {
        "latitude": lat,
        "longitude": lon,
        "windows": visible_windows
    }


def get_blocking_angle(target_az: float, terrain_map) -> float:
    """
    Function to get visibility angle of Earth using target azimuth from a terrain map
    :param lat: azimuth in degrees (0 to 360)
    :type lat: float
    :param lon: terrain map from terrain_horizon
    :type lon: dict
    :return: minimal angle where Earth is visible
    :rtype: float
    """
    if not terrain_map:
        return 0.0
    # Circular distance handles wrap-around (e.g., 359° is 2° away from 1°)
    closest_az = min(
        terrain_map.keys(),
        key=lambda a: min(abs(a - target_az), 360 - abs(a - target_az))
    )
    blocking_angle = terrain_map[closest_az]
    min_visible_angle = blocking_angle if blocking_angle is not None else 0.0
    return min_visible_angle


def get_horizons_visibility_windows(lat: float, lon: float):
    """
    Function to fetch Visibility windows from JPL Horizons API
    :param lat: Latitude in degrees (-90 to 90)
    :type lat: float
    :param lon: Longitude in degrees (-180 to 360)
    :type lon: float
    :return: Match obj with all visibility matches, or None if no data
    :rtype: Match | None
    """
    params = {
        "format": "json",
        "COMMAND": "'399'",  # 399 = Earth
        "EPHEM_TYPE": "'OBSERVER'",
        "CENTER": "'coord@301'",    # 301 = The Moon
        "SITE_COORD": f"'{lon},{lat},0'",
        "START_TIME": "'2026-10-01'",
        "STOP_TIME": "'2026-10-31 23:59'",
        "STEP_SIZE": "'1 h'",
        "QUANTITIES": "'4'",    # 4 = Apparent Azimuth & Elevation
        "CSV_FORMAT": "'YES'"
    }

    response = requests.get(HORIZONS_API_URL, params=params, timeout=15)
    if response.status_code != 200:
        return None

    raw_resp = response.json().get("result", "")
    # read lines between $$SOE (start of ephemeris) and $$EOE (end of ephemeris)
    match = re.search(r"\$\$SOE\s*(.*?)\s*\$\$EOE", raw_resp, re.DOTALL)
    if not match:
        return None

    return match
