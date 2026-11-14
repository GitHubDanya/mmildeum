from functools import cache
from math import isfinite
from pathlib import Path

import rasterio
from numpy.ma import is_masked
from pyproj import CRS, Transformer
from pyproj.exceptions import ProjError
from rasterio.crs import CRS as RasterCRS
from rasterio.errors import RasterioError
from rasterio.transform import rowcol
from rasterio.windows import Window

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
TERRAIN_MAP = DATA_DIR / "LDRM_80S_1000MPP_ADJ_CLASS.TIF"
ELEVATION_MAP = DATA_DIR / "LDEM_80S_80MPP_ADJ.TIF"


class TerrainDataUnavailable(RuntimeError):
    pass


def _in_south_pole_coverage(lat: float, lon: float) -> bool:
    """
    Check if a lunar coordinate is inside the south pole maps (80°S to the pole).
    :param lat: Latitude in degrees (-90 to 90)
    :type lat: float
    :param lon: Longitude in degrees (-180 to 360)
    :type lon: float
    :return: True if the coordinate is at or below 80°S, False otherwise
    :rtype: bool
    """
    if not -90 <= lat <= 90:
        raise ValueError("[terrain.py] Lunar latitude must be between -90 and 90 degrees!")
    if not -180 <= lon <= 360:
        raise ValueError("[terrain.py] Lunar longitude must be between -180 and 360 degrees!")
    return lat <= -80


@cache
def _map_transformer(raster_crs: RasterCRS | None) -> Transformer:
    """
    Build a cached transformer from lunar longitude and latitude to projected map coordinates.
    :param raster_crs: CRS of the raster being sampled
    :type raster_crs: RasterCRS | None
    :return: Transformer from the CRS's geodetic lon/lat to its projected x/y (always_xy order)
    :rtype: Transformer
    """
    if raster_crs is None or not raster_crs.is_projected:
        raise TerrainDataUnavailable("[terrain.py] Expected a projected lunar CRS!")

    map_src = CRS.from_wkt(raster_crs.to_wkt())
    return Transformer.from_crs(map_src.geodetic_crs, map_src, always_xy=True)


def _project(transformer: Transformer, lat: float, lon: float) -> tuple[float, float]:
    """
    Project a lunar coordinate to map x/y, normalizing longitude to [-180, 180).
    :param transformer: Transformer from _map_transformer for the target raster
    :type transformer: Transformer
    :param lat: Latitude in degrees (-90 to 90)
    :type lat: float
    :param lon: Longitude in degrees (-180 to 360)
    :type lon: float
    :return: Projected (x, y) in the raster's map units
    :rtype: tuple[float, float]
    """
    longitude = 0.0 if lat == -90 else (lon + 180) % 360 - 180

    try:
        return transformer.transform(longitude, lat, errcheck=True)
    except ProjError as e:
        raise TerrainDataUnavailable("[terrain.py] Could not project the lunar coordinate!") from e


@cache
def _load_terrain_map():
    """
    Load and cache the LOLA roughness class map.
    :return: Masked class array (band 1), affine transform, and lon/lat-to-map transformer
    :rtype: tuple[numpy.ma.MaskedArray, affine.Affine, Transformer]
    """
    try:
        with rasterio.open(TERRAIN_MAP) as raster:
            transformer = _map_transformer(raster.crs)
            return raster.read(1, masked=True), raster.transform, transformer
    except (OSError, RasterioError, ProjError) as error:
        raise TerrainDataUnavailable("[terrain.py] Could not load the LOLA terrain map!") from error


def get_terrain_type(lat: float, lon: float) -> int | None:
    """
    Get the LOLA roughness class at a lunar coordinate.
    :param lat: Latitude in degrees (-90 to 90)
    :type lat: float
    :param lon: Longitude in degrees (-180 to 360)
    :type lon: float
    :return: Roughness class ID, or None outside coverage or where the pixel has no data
    :rtype: int | None
    """
    if not _in_south_pole_coverage(lat, lon):
        return None

    classes, affine, transformer = _load_terrain_map()
    row, col = rowcol(affine, *_project(transformer, lat, lon))
    height, width = classes.shape

    if not (0 <= row < height and 0 <= col < width):
        return None

    pixel = classes[row, col]
    if is_masked(pixel) or not isfinite(pixel):
        return None

    return int(pixel)


def get_terrain_elevation(lat: float, lon: float) -> float | None:
    """
    Get the LOLA elevation at a lunar coordinate by reading a single pixel.
    :param lat: Latitude in degrees (-90 to 90)
    :type lat: float
    :param lon: Longitude in degrees (-180 to 360)
    :type lon: float
    :return: Elevation with the band's scale and offset applied, or None if unavailable
    :rtype: float | None
    """
    if not _in_south_pole_coverage(lat, lon):
        return None

    try:
        if not ELEVATION_MAP.is_file():
            return None

        with rasterio.open(ELEVATION_MAP) as raster:
            x, y = _project(_map_transformer(raster.crs), lat, lon)
            row, col = raster.index(x, y)

            if not (0 <= row < raster.height and 0 <= col < raster.width):
                return None

            pixel = raster.read(1, window=Window(col, row, 1, 1), masked=True)[0, 0]
            if is_masked(pixel):
                return None

            elevation = float(pixel) * raster.scales[0] + raster.offsets[0]
            return elevation if isfinite(elevation) else None
    except (OSError, RasterioError, ProjError) as e:
        raise TerrainDataUnavailable("[terrain.py] Could not read the LOLA elevation map!") from e