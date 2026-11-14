import logging
from fastapi import APIRouter, HTTPException, Query
from .schemas import FetchDataResponse
from .services.terrain import (TerrainDataUnavailable, get_terrain_elevation, get_terrain_type,)

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

@router.get("/fetch-data", response_model=FetchDataResponse)
def fetch_data(lat: float = Query(ge=-90, le=90), long: float = Query(ge=-180, le=360), time: str | None = Query(None, description="Used by time-depend. site data")) -> FetchDataResponse:
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
        elevation_m = get_terrain_elevation(lat, long)
    except TerrainDataUnavailable as e:
        logger.exception("[routes.py] Terrain lookup failed!")
        raise HTTPException(status_code=503, detail="Lunar terrain data is unavailable!") from e
    return FetchDataResponse(terrain_type=None if class_id is None else f"LOLA roughness class {class_id}", terrain_class_id=class_id, terrain_elevation_m=elevation_m)
