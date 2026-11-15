import requests
import re

from .evaluation import (
    EPHEMERIS_START,
    EPHEMERIS_STEP,
    EPHEMERIS_STEP_HOURS,
    EPHEMERIS_STOP,
    availability_metrics,
)

HORIZONS_API_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"

def get_average_sun_angle(lat: float, lon: float) -> dict | None:
    """
    Function to get the Average sun angle at a lunar coordinate
    :param lat: Latitude in degrees (-90 to 90)
    :type lat: float
    :param lon: Longitude in degrees (-180 to 360)
    :type lon: float
    :return: Dictionary with average Sun angle at Daytime & Full Moon Cycle, or None if no data
    :rtype: dict | None
    """
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 360):
        return None

    params = {
        "format": "json",
        "COMMAND": "'10'",  # 10 = The Sun
        "EPHEM_TYPE": "'OBSERVER'",
        "CENTER": "'coord@301'",    # 301 = The Moon
        "SITE_COORD": f"'{lon},{lat},0'",
        "START_TIME": f"'{EPHEMERIS_START}'",
        "STOP_TIME": f"'{EPHEMERIS_STOP}'",
        "STEP_SIZE": f"'{EPHEMERIS_STEP}'",
        "QUANTITIES": "'4'",    # 4 = Apparent Azimuth & Elevation
        "CSV_FORMAT": "'YES'"   # Makes parsing much cleaner
    }

    try:
        response = requests.get(HORIZONS_API_URL, params=params, timeout=15)
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None

    raw_resp = response.json().get("result", "")
    # read lines between $$SOE (start of ephemeris) and $$EOE (end of ephemeris)
    match = re.search(r"\$\$SOE\s*(.*?)\s*\$\$EOE", raw_resp, re.DOTALL)
    if not match:
        return None

    lines = match.group(1).strip().splitlines()
    all_elevations = []
    daytime_elevations = []
    illuminated_samples = []

    for line in lines:
        parts = []
        for p in line.split(","):
            if p.strip():
                parts.append(p.strip())

        try:
            elevation = float(parts[-1])    # Elevation is the last numeric field
            all_elevations.append(elevation)
            illuminated_samples.append(elevation > 0)
            if elevation > 0:
                daytime_elevations.append(elevation)
        except (IndexError, ValueError):
            continue

    metrics = availability_metrics(illuminated_samples)
    if metrics is None:
        return None

    sunlight_fraction, longest_darkness_hours = metrics

    avg_daytime = round(sum(daytime_elevations) / len(daytime_elevations), 2) if daytime_elevations else 0.0
    avg_full_cycle = round(sum(all_elevations) / len(all_elevations), 2) if all_elevations else 0.0

    return {
        "latitude": lat,
        "longitude": lon,
        "avg_daytime_sun_angle": avg_daytime,
        "avg_full_cycle_sun_angle": avg_full_cycle,
        "daylight_percentage": round(sunlight_fraction * 100, 1),
        "sunlight_fraction": sunlight_fraction,
        "longest_darkness_hours": longest_darkness_hours,
        "sample_count": len(illuminated_samples),
        "time_step_hours": EPHEMERIS_STEP_HOURS,
        "period_start": EPHEMERIS_START,
        "period_stop": EPHEMERIS_STOP,
    }
