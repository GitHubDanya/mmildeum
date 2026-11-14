from functools import cache
from math import atan2, cos, degrees, floor, hypot, isfinite, radians, sin
from pathlib import Path
import rasterio
from numpy.ma import is_masked
from pyproj import CRS, Geod, Transformer
from pyproj.exceptions import ProjError
from rasterio.crs import CRS as RasterCRS
from rasterio.errors import RasterioError
from rasterio.transform import rowcol
from rasterio.windows import Window

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
TERRAIN_MAP = DATA_DIR / "LDRM_80S_1000MPP_ADJ_CLASS.TIF"
ELEVATION_MAP = DATA_DIR / "LDEM_80S_80MPP_ADJ.TIF"
SLOPE_MAP = DATA_DIR / "LDSM_80S_80MPP_ADJ.TIF"
GLOBAL_ELEVATION_MAP = DATA_DIR / "LDEM64_PA_pixel_202405.tif"
MOON_RADIUS_M = 1_737_400.0
GLOBAL_PIXEL_M = MOON_RADIUS_M * radians(1 / 64)
GLOBAL_GEOD = Geod(a=MOON_RADIUS_M, f=0)
# NAIF moon_080317.tf, frame 31007. Convert frame rotations to active rotations.
PA_Z, PA_Y, PA_X = (radians(-angle / 3600) for angle in (67.92, 78.56, 0.30))

class TerrainDataUnavailable(RuntimeError):
    """
    Raised when a LOLA terrain map cannot be loaded, read, or projected
    """


def _in_south_pole_coverage(lat: float, lon: float) -> bool:
    """
    Function to check if a lunar coordinate is inside the south pole maps (80°S to the pole)
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
    Function to build a cached transformer from lunar longitude and latitude to projected map coordinates
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
    Function to project a lunar coordinate to map x/y, normalizing longitude to [-180, 180)
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
    Function to load and cache the LOLA roughness class map.
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
    Function to get the LOLA roughness class at a lunar coordinate
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


def _sample_terrain_map(path: Path, map_name: str, lat: float, lon: float) -> float | None:
    """
    Function to read a single pixel from a LOLA south pole raster at a lunar coordinate
    :param path: Path to the GeoTIFF to sample
    :type path: Path
    :param map_name: Human-readable map name used in the error message (e.g. "elevation")
    :type map_name: str
    :param lat: Latitude in degrees (-90 to 90)
    :type lat: float
    :param lon: Longitude in degrees (-180 to 360)
    :type lon: float
    :return: Pixel value with the band's scale and offset applied
    :rtype: float | None
    """
    if not _in_south_pole_coverage(lat, lon):
        return None
    try:
        if not path.is_file():
            return None

        with rasterio.open(path) as raster:
            x, y = _project(_map_transformer(raster.crs), lat, lon)
            row, col = raster.index(x, y)
            if not (0 <= row < raster.height and 0 <= col < raster.width):
                return None
            pixel = raster.read(1, window=Window(col, row, 1, 1), masked=True)[0, 0]
            if is_masked(pixel):
                return None
            value = float(pixel) * raster.scales[0] + raster.offsets[0]
            return value if isfinite(value) else None
    except (OSError, RasterioError, ProjError) as e:
        raise TerrainDataUnavailable(f"[terrain.py] Could not read the LOLA {map_name} map!") from e


def _moon_me_to_pa(lat: float, lon: float) -> tuple[float, float]:
    """Convert DE421 Mean Earth coordinates to PA longitude and latitude."""
    lat_rad = radians(lat)
    lon_rad = radians(lon % 360)
    x = cos(lat_rad) * cos(lon_rad)
    y = cos(lat_rad) * sin(lon_rad)
    z = sin(lat_rad)

    y, z = cos(PA_X) * y - sin(PA_X) * z, sin(PA_X) * y + cos(PA_X) * z
    x, z = cos(PA_Y) * x + sin(PA_Y) * z, -sin(PA_Y) * x + cos(PA_Y) * z
    x, y = cos(PA_Z) * x - sin(PA_Z) * y, sin(PA_Z) * x + cos(PA_Z) * y

    return degrees(atan2(y, x)), degrees(atan2(z, hypot(x, y)))


def _read_global_pixel(raster, lon: float, lat: float) -> float | None:
    """Read one pixel from the global cylindrical grid in PA coordinates."""
    if raster.crs is not None and raster.crs.is_projected:
        x, y = _map_transformer(raster.crs).transform(lon, lat, errcheck=True)
    else:
        x, y = lon, lat

    col, row = ~raster.transform * (x, y)
    if not -1e-8 <= row <= raster.height + 1e-8:
        return None

    # Wrap longitude at the seam and map the exact poles to the edge rows.
    col = floor(col) % raster.width
    row = min(max(floor(row), 0), raster.height - 1)
    pixel = raster.read(1, window=Window(col, row, 1, 1), masked=True)[0, 0]
    if is_masked(pixel):
        return None

    value = float(pixel) * raster.scales[0] + raster.offsets[0]
    return value if isfinite(value) else None


def _read_global_terrain(lat: float, lon: float, *, slope: bool = False) -> float | None:
    """Read global elevation or estimate slope from four nearby elevations."""
    try:
        if not GLOBAL_ELEVATION_MAP.is_file():
            return None

        lon_pa, lat_pa = _moon_me_to_pa(lat, lon)
        with rasterio.open(GLOBAL_ELEVATION_MAP) as raster:
            if not slope:
                return _read_global_pixel(raster, lon_pa, lat_pa)

            samples = []
            for azimuth in (90, 270, 0, 180):
                lon_near, lat_near, _ = GLOBAL_GEOD.fwd(
                    lon_pa, lat_pa, azimuth, GLOBAL_PIXEL_M
                )
                elevation = _read_global_pixel(raster, lon_near, lat_near)
                if elevation is None:
                    return None
                samples.append(elevation)

            east, west, north, south = samples
            rise = hypot(east - west, north - south)
            return degrees(atan2(rise, 2 * GLOBAL_PIXEL_M))
    except (OSError, RasterioError, ProjError) as error:
        raise TerrainDataUnavailable(
            "[terrain.py] Could not read the global LOLA elevation map!"
        ) from error


def get_terrain_elevation(lat: float, lon: float) -> float | None:
    """Return elevation in meters, preferring the south-pole map."""
    elevation = _sample_terrain_map(ELEVATION_MAP, "elevation", lat, lon)
    if elevation is not None:
        return elevation
    return _read_global_terrain(lat, lon)


def get_ground_angle(lat: float, lon: float) -> float | None:
    """Return slope in degrees, preferring the south-pole slope map."""
    angle = _sample_terrain_map(SLOPE_MAP, "slope", lat, lon)
    if angle is not None and 0 <= angle <= 90:
        return angle
    return _read_global_terrain(lat, lon, slope=True)