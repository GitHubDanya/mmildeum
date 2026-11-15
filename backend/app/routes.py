import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from .schemas import FetchDataResponse, SunlightDurationResponse
from .services.earth_visibility import get_earth_visibility_window
from .services.evaluation import DEFAULT_FOOTPRINT_RADIUS_M
from .services.scoring import score_site
from .services.sun_angle import get_average_sun_angle
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

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


@router.get("/fetch-data", response_model=FetchDataResponse)
def fetch_data(lat: float = Query(ge=-90, le=90, description="Lunar latitude in degrees. Elevation and slope have global coverage when the global DEM is available.",), long: float = Query(ge=-180, le=360, description=("Lunar longitude in degrees. Accepts -180° to 180° or 0° to 360°. Positive values are eastward!"),), time: str | None = Query(None, description="Reserved for time-dependent site data."), footprint_radius_m: float = Query(DEFAULT_FOOTPRINT_RADIUS_M, gt=0, le=5_000, description="Radius in metres of the circular slope-sampling footprint.",),) -> FetchDataResponse:
    """
    Function to fetch the site data at a lunar coordinate
    :param lat: Latitude in degrees (-90 to 90)
    :type lat: float
    :param long: Longitude in degrees (-180 to 360)
    :type long: float
    :param time: Time for time-dependent site data (currently unused)
    :type time: str | None
    :param footprint_radius_m: Radius of the circular slope-sampling footprint
    :type footprint_radius_m: float
    :return: Site data, scoring inputs, provenance, and suitability score
    :rtype: FetchDataResponse
    """
    try:
        lola_roughness_deg = get_lola_roughness_deg(lat, long)
        sun_data = get_average_sun_angle(lat, long)
        elevation_m = get_terrain_elevation(lat, long)
        ground_angle_deg = get_ground_angle(lat, long)
        visibility_wins = get_earth_visibility_window(lat, long)
        slope_footprint = get_slope_footprint_p95(lat, long, footprint_radius_m,)
    except TerrainDataUnavailable as e:
        logger.exception("[routes.py] Terrain lookup failed!")
        raise HTTPException(status_code=503, detail="Lunar terrain data is unavailable!") from e
    scoring_metrics = {
        "sunlight_fraction": (sun_data.get("sunlight_fraction") if sun_data else None),
        "longest_darkness_hours": (sun_data.get("longest_darkness_hours") if sun_data else None),
        "earth_visibility_fraction": (visibility_wins.get("earth_visibility_fraction") if visibility_wins else None),
        "longest_earth_blackout_hours": (visibility_wins.get("longest_earth_blackout_hours") if visibility_wins else None),
        "slope_p95_degrees": (slope_footprint.get("slope_p95_degrees") if slope_footprint else None),
    }
    scoring_result = score_site(
        {
            **scoring_metrics,
            "source_coverage": {
                "solar_ephemeris": sun_data is not None,
                "earth_ephemeris": (visibility_wins is not None and visibility_wins.get("earth_visibility_fraction") is not None),
                "dem": slope_footprint is not None,
                "slope_footprint": slope_footprint is not None,
            },
            "metadata": {
                "period_start": (sun_data.get("period_start") if sun_data else None),
                "period_stop": (sun_data.get("period_stop") if sun_data else None),
                "time_step_hours": (sun_data.get("time_step_hours") if sun_data else None),
                "footprint_radius_m": footprint_radius_m,
                "slope_sample_count": (slope_footprint.get("sample_count") if slope_footprint else 0),
                "data_sources": ["JPL Horizons solar ephemeris", "JPL Horizons Earth ephemeris", "LOLA digital elevation model",],
            },
        }
    )
    return FetchDataResponse(daytime_avg_sun_angle=sun_data["avg_daytime_sun_angle"] if sun_data else None, terrain_elevation_m=elevation_m, visibility_windows=visibility_wins["windows"] if visibility_wins else None, ground_angle_deg=ground_angle_deg, lola_roughness_deg=lola_roughness_deg, score=scoring_result["score"], scoring_metrics=scoring_metrics, scoring=scoring_result,)



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
