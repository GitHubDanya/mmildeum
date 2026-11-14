import logging
from fastapi import APIRouter, HTTPException, Query
from .schemas import FetchDataResponse, SunlightDurationResponse
from .services.sun_angle import get_average_sun_angle
from .services.terrain import (
    TerrainDataUnavailable,
    get_ground_angle,
    get_lola_roughness_deg,
    get_terrain_elevation,
)
from .services.earth_visibility import get_earth_visibility_window
from datetime import datetime
from .services.sunlight_duration import (
    SunlightDataUnavailable,
    get_average_duration_of_sunlight,
)

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


@router.get("/fetch-data", response_model=FetchDataResponse)
def fetch_data(
    lat: float = Query(
        ge=-90,
        le=90,
        description="Lunar latitude in degrees. Elevation and slope have global coverage when the global DEM is available.",
    ),
    long: float = Query(
        ge=-180,
        le=360,
        description=(
            "Lunar longitude in degrees. Accepts -180° to 180° or 0° to 360°. Positive values are eastward!"
        ),
    ),
    time: str | None = Query(
        None, description="Reserved for time-dependent site data."
    ),
) -> FetchDataResponse:
    """
    Function to fetch the site data at a lunar coordinate
    :param lat: Latitude in degrees (-90 to 90)
    :type lat: float
    :param long: Longitude in degrees (-180 to 360)
    :type long: float
    :param time: Time for time-dependent site data (currently unused)
    :type time: str | None
    :return: Site data with the published global LOLA roughness when available
    :rtype: FetchDataResponse
    """
    try:
        lola_roughness_deg = get_lola_roughness_deg(lat, long)
        sun_data = get_average_sun_angle(lat, long)
        elevation_m = get_terrain_elevation(lat, long)
        ground_angle_deg = get_ground_angle(lat, long)
        visibility_wins = get_earth_visibility_window(lat, long)
    except TerrainDataUnavailable as e:
        logger.exception("[routes.py] Terrain lookup failed!")
        raise HTTPException(
            status_code=503, detail="Lunar terrain data is unavailable!"
        ) from e
    return FetchDataResponse(
        daytime_avg_sun_angle=sun_data["avg_daytime_sun_angle"] if sun_data else None,
        terrain_elevation_m=elevation_m,
        visibility_windows=visibility_wins["windows"] if visibility_wins else None,
        ground_angle_deg=ground_angle_deg,
        lola_roughness_deg=lola_roughness_deg,
    )



@router.get("/sunlight-duration", response_model=SunlightDurationResponse)
def sunlight_duration(
    lat: float = Query(ge=-90, le=90),
    long: float = Query(ge=-180, le=360),
    start: datetime = Query(description="UTC-aware start of the interval"),
    end: datetime = Query(description="UTC-aware end of the interval"),
    step_minutes: int = Query(default=60, ge=1, le=1440),
) -> SunlightDurationResponse:
    """Calculate sunlight duration for a selected lunar mission interval.

    Args:
        lat: Lunar latitude in degrees.
        long: East-positive lunar longitude in degrees.
        start: Start of the analysis interval with timezone.
        end: End of the analysis interval with timezone.
        step_minutes: Interval sampling step in minutes.

    Returns:
        Validated sunlight duration measurements.
    """
    try:
        result = get_average_duration_of_sunlight(
            lat,
            long,
            start,
            end,
            step_minutes=step_minutes,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except (TerrainDataUnavailable, SunlightDataUnavailable) as exc:
        logger.warning("Sunlight duration lookup failed: %s", exc)

        raise HTTPException(
            status_code=503,
            detail="Required lunar illumination data is unavailable",
        ) from exc

    return SunlightDurationResponse(**result)
