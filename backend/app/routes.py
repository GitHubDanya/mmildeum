import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from .schemas import FetchDataResponse
from .services.earth_visibility import (
    EarthVisibilityDataUnavailable,
    get_earth_visibility_window,
)
from .services.evaluation import (
    DEFAULT_FOOTPRINT_RADIUS_M,
    validate_interval,
)
from .services.scoring import score_site
from .services.sunlight_duration import (
    SunlightDataUnavailable,
    get_average_duration_of_sunlight,
)
from .services.terrain import (
    TerrainDataUnavailable,
    get_ground_angle,
    get_lola_roughness_deg,
    get_slope_footprint_p95,
    get_terrain_elevation,
)
from .services.terrain_horizon import get_terrain_horizon


router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


@router.get("/fetch-data", response_model=FetchDataResponse)
def fetch_data(
    lat: float = Query(
        ge=-90,
        le=90,
        description="Lunar latitude in degrees.",
    ),
    long: float = Query(
        ge=-180,
        le=360,
        description="East-positive lunar longitude in degrees.",
    ),
    mission_start: datetime = Query(
        description="UTC-aware start of the mission evaluation interval.",
    ),
    mission_end: datetime = Query(
        description="UTC-aware end of the mission evaluation interval.",
    ),
    step: int = Query(
        default=60,
        ge=1,
        le=1440,
        description="Ephemeris sampling interval in whole minutes.",
    ),
    footprint_radius_m: float = Query(
        DEFAULT_FOOTPRINT_RADIUS_M,
        gt=0,
        le=5_000,
        description="Radius in metres of the slope-sampling footprint.",
    ),
) -> FetchDataResponse:
    """Evaluate a lunar site over one mission interval and return its score."""
    step_minutes = step

    try:
        start, end, sample_count = validate_interval(
            mission_start,
            mission_end,
            step_minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        horizon_data = get_terrain_horizon(lat, long)
        lola_roughness_deg = get_lola_roughness_deg(lat, long)
        elevation_m = get_terrain_elevation(lat, long)
        ground_angle_deg = get_ground_angle(lat, long)
        slope_footprint = get_slope_footprint_p95(
            lat,
            long,
            footprint_radius_m,
        )
    except TerrainDataUnavailable as exc:
        logger.exception("Terrain lookup failed")
        raise HTTPException(
            status_code=503,
            detail="Lunar terrain data is unavailable",
        ) from exc

    try:
        sun_data = get_average_duration_of_sunlight(
            lat,
            long,
            start,
            end,
            step_minutes=step_minutes,
            horizon_data=horizon_data,
        )
    except SunlightDataUnavailable as exc:
        logger.warning("Solar ephemeris lookup failed: %s", exc)
        sun_data = None

    try:
        earth_data = get_earth_visibility_window(
            lat,
            long,
            start,
            end,
            step_minutes=step_minutes,
            horizon_data=horizon_data,
        )
    except EarthVisibilityDataUnavailable as exc:
        logger.warning("Earth ephemeris lookup failed: %s", exc)
        earth_data = None

    scoring_metrics = {
        "sunlight_fraction": (
            sun_data.get("sunlight_fraction") if sun_data else None
        ),
        "longest_darkness_hours": (
            sun_data.get("longest_darkness_hours") if sun_data else None
        ),
        "earth_visibility_fraction": (
            earth_data.get("earth_visibility_fraction")
            if earth_data
            else None
        ),
        "longest_earth_blackout_hours": (
            earth_data.get("longest_earth_blackout_hours")
            if earth_data
            else None
        ),
        "slope_p95_degrees": (
            slope_footprint.get("slope_p95_degrees")
            if slope_footprint
            else None
        ),
    }

    solar_available = scoring_metrics["sunlight_fraction"] is not None
    earth_available = scoring_metrics["earth_visibility_fraction"] is not None
    slope_available = slope_footprint is not None

    scoring_result = score_site(
        {
            **scoring_metrics,
            "source_coverage": {
                "solar_ephemeris": solar_available,
                "earth_ephemeris": earth_available,
                "dem": slope_available,
                "slope_footprint": slope_available,
            },
            "metadata": {
                "period_start": start.isoformat(),
                "period_stop": end.isoformat(),
                "time_step_minutes": step_minutes,
                "sample_count": sample_count,
                "footprint_radius_m": footprint_radius_m,
                "slope_sample_count": (
                    slope_footprint.get("sample_count")
                    if slope_footprint
                    else 0
                ),
                "horizon_data_quality": horizon_data.get("data_quality"),
                "data_sources": [
                    "JPL Horizons solar ephemeris",
                    "JPL Horizons Earth ephemeris",
                    "LOLA digital elevation model",
                ],
            },
        }
    )

    return FetchDataResponse(
        mission_start=start,
        mission_end=end,
        step_minutes=step_minutes,
        sunlight_windows=(
            sun_data.get("sunlight_windows") if sun_data else None
        ),
        visibility_windows=(
            earth_data.get("windows") if earth_data else None
        ),
        terrain_elevation_m=elevation_m,
        ground_angle_deg=ground_angle_deg,
        lola_roughness_deg=lola_roughness_deg,
        score=scoring_result["score"],
        scoring_metrics=scoring_metrics,
        scoring=scoring_result,
    )
