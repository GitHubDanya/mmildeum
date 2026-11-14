import logging
from fastapi import APIRouter, HTTPException, Query
from .schemas import FetchDataResponse, TerrainRoughnessMetadata
from .services.sun_angle import get_average_sun_angle
from .services.terrain import (
    TerrainDataUnavailable,
    get_ground_angle,
    get_terrain_elevation,
    get_terrain_roughness,
    get_terrain_type,
)

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

@router.get("/fetch-data", response_model=FetchDataResponse)
def fetch_data(lat: float = Query(ge=-90, le=90, description="Lunar latitude in degrees. Elevation and slope have global coverage when the global DEM is available.",), long: float = Query(ge=-180, le=360, description=("Lunar longitude in degrees. Accepts -180° to 180° or 0° to 360°. Positive values are eastward!"),), time: str | None = Query(None, description="Reserved for time-dependent site data.")) -> FetchDataResponse:
    """
    Function to fetch the site data at a lunar coordinate
    :param lat: Latitude in degrees (-90 to 90)
    :type lat: float
    :param long: Longitude in degrees (-180 to 360)
    :type long: float
    :param time: Time for time-dependent site data (currently unused)
    :type time: str | None
    :return: Site data with the published NASA class and a DEM-based roughness estimate when available
    :rtype: FetchDataResponse
    """
    try:
        class_id = get_terrain_type(lat, long)
        roughness = get_terrain_roughness(lat, long)
        sun_data = get_average_sun_angle(lat, long)
        elevation_m = get_terrain_elevation(lat, long)
        ground_angle_deg = get_ground_angle(lat, long)
    except TerrainDataUnavailable as e:
        logger.exception("[routes.py] Terrain lookup failed!")
        raise HTTPException(status_code=503, detail="Lunar terrain data is unavailable!") from e
    return FetchDataResponse(
        terrain_type=f"LOLA roughness class {class_id}" if class_id is not None else None,
        terrain_class_id=class_id,
        daytime_avg_sun_angle=sun_data["avg_daytime_sun_angle"] if sun_data else None,
        terrain_elevation_m=elevation_m,
        ground_angle_deg=ground_angle_deg,
        terrain_roughness_m=roughness.value_m if roughness is not None else None,
        terrain_roughness_metadata=(
            TerrainRoughnessMetadata.model_validate(roughness, from_attributes=True)
            if roughness is not None else None
        ),
    )
