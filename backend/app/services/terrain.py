from functools import cache
from math import isfinite
from pathlib import Path
import rasterio
from numpy.ma import is_masked
from pyproj import CRS, Transformer
from pyproj.exceptions import ProjError
from rasterio.errors import RasterioError
from rasterio.transform import rowcol

TERRAIN_MAP = (Path(__file__).resolve().parents[2]) / "data" / "LDRM_80S_1000MPP_ADJ_CLASS.TIF"


class TerrainDataUnavailable(RuntimeError):
    pass


@cache
def _load_terrain_map():
    """
    Function to load the terrain map and its coordinate transformer (cached)
    :return: Terrain class grid, affine transform and lon/lat to map transformer
    :rtype: tuple[numpy.ma.MaskedArray, affine.Affine, pyproj.Transformer]
    """
    try:
        with rasterio.open(TERRAIN_MAP) as raster:
            if raster.crs is None or not raster.crs.is_projected:
                raise TerrainDataUnavailable("[terrain.py] Expected a projected lunar CRS!")
            map_crs = CRS.from_wkt(raster.crs.to_wkt())
            to_map = Transformer.from_crs(map_crs.geodetic_crs, map_crs, always_xy=True)
            return raster.read(1, masked=True), raster.transform, to_map
    except(OSError, RasterioError, ProjError) as e:
        raise TerrainDataUnavailable("[terrain.py] Could not load LOLA terrain map!") from e


def get_terrain_type(lat: float, lon: float) -> int | None:
    """
    Function to get the terrain class at a lunar coordinate
    :param lat: Latitude in degrees (-90 to 90)
    :type lat: float
    :param lon: Longitude in degrees (-180 to 360)
    :type lon: float
    :return: Terrain class, or None if outside the map or no data
    :rtype: int | None
    """
    if not (-90 <= lat <= 90 and -180 <= lon <= 360):
        raise ValueError("[terrain.py] Invalid lunar latitude or longitude!")
    if lat > -80:
        return None

    classes, affine, to_map = _load_terrain_map()
    lon = 0.0 if lat == -90 else (lon + 180) % 360 - 180

    try:
        x, y = to_map.transform(lon, lat, errcheck=True)
    except ProjError as e:
        raise TerrainDataUnavailable("[terrain.py] Could not project the lunar coordinate!") from e

    row, col = rowcol(affine, x, y)
    height, width = classes.shape
    if not (0 <= row < height and 0 <= col < width):
        return None

    pixel = classes[row, col]
    if is_masked(pixel) or not isfinite(pixel):
        return None
    return int(pixel)
