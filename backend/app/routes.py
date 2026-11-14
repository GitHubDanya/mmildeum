import logging
from fastapi import APIRouter, HTTPException, Query
from .schemas import FetchDataResponse
from .services.terrain import TerrainDataUnavailable, get_terrain_type
from .services.sun_angle import get_average_sun_angle

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

@router.get("/fetch-data", response_model=FetchDataResponse)
def fetch_data(lat: float = Query(ge=-90, le=90, description="Lunar latitude in degrees. The LOLA map covers 80°S to 90°S.",), long: float = Query(ge=-180, le=360, description=("Lunar longitude in degrees. Accepts -180° to 180° or 0° to 360°. Positive values are eastward!"),), time: str | None = Query(None, description="Reserved for time-dependent site data.")) -> FetchDataResponse:
    """
    Function to fetch the site data at a lunar coordinate
    :param lat: Latitude in degrees (-90 to 90)
    :type lat: float
    :param long: Longitude in degrees (-180 to 360)
    :type long: float
    :param time: Time for time-dependent site data (currently unused)
    :type time: str | None
    :return: Terrain type label and class ID, both None if outside the map or no data
    :rtype: FetchDataResponse
    """
    try:
        class_id = get_terrain_type(lat, long)
        daytime_avg_sun_angle = get_average_sun_angle(lat, long)["avg_daytime_sun_angle"]
    except TerrainDataUnavailable as e:
        logger.exception("[routes.py] Terrain lookup failed!")
        raise HTTPException(status_code=503, detail="Lunar terrain data is unavailable!") from e
    return FetchDataResponse(terrain_type=None if class_id is None else f"LOLA roughness class {class_id}", terrain_class_id=class_id, daytime_avg_sun_angle=daytime_avg_sun_angle)
