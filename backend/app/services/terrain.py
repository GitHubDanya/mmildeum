"""LOLA elevation, slope, and roughness at lunar coordinates."""

from functools import cache
from math import atan2, cos, degrees, floor, hypot, isfinite, radians, sin
from os import fstat
from pathlib import Path
from struct import Struct

import rasterio
from numpy.ma import is_masked
from pyproj import CRS, Geod, Transformer
from pyproj.exceptions import ProjError
from rasterio.crs import CRS as RasterCRS
from rasterio.errors import RasterioError
from rasterio.windows import Window

from .evaluation import DEFAULT_FOOTPRINT_RADIUS_M

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
ELEVATION_MAP = DATA_DIR / "LDEM_80S_80MPP_ADJ.TIF"
SLOPE_MAP = DATA_DIR / "LDSM_80S_80MPP_ADJ.TIF"
GLOBAL_ELEVATION_MAP = DATA_DIR / "LDEM64_PA_pixel_202405.tif"

#PDS MAS_225M_16 V1.0, MOON_ME DE421.
LOLA_ROUGHNESS_MAP = DATA_DIR / "MAS_225M_16.IMG"
LOLA_ROUGHNESS_PIXELS_PER_DEGREE = 16
LOLA_ROUGHNESS_WIDTH = 360 * LOLA_ROUGHNESS_PIXELS_PER_DEGREE
LOLA_ROUGHNESS_HEIGHT = 180 * LOLA_ROUGHNESS_PIXELS_PER_DEGREE
LOLA_ROUGHNESS_SAMPLE = Struct("<h")
LOLA_ROUGHNESS_FILE_SIZE = (LOLA_ROUGHNESS_WIDTH * LOLA_ROUGHNESS_HEIGHT * LOLA_ROUGHNESS_SAMPLE.size)

MOON_RADIUS_M = 1_737_400.0
GLOBAL_PIXEL_M = MOON_RADIUS_M * radians(1 / 64)
GLOBAL_GEOD = Geod(a=MOON_RADIUS_M, f=0)
#NAIF moon_080317.tf, frame 31007. Convert frame rotations to active rotations
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
    _validate_coordinates(lat, lon)
    return lat <= -80


def _validate_coordinates(lat: float, lon: float) -> None:
    """
    Function to check that a lunar coordinate is within the accepted latitude and longitude ranges
    :param lat: Latitude in degrees (-90 to 90)
    :type lat: float
    :param lon: Longitude in degrees (-180 to 360)
    :type lon: float
    :raises ValueError: If the latitude or longitude is out of range
    """
    if not -90 <= lat <= 90:
        raise ValueError("[terrain.py] Lunar latitude must be between -90 and 90 degrees!")
    if not -180 <= lon <= 360:
        raise ValueError("[terrain.py] Lunar longitude must be between -180 and 360 degrees!")


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
    """
    Function to rotate a lunar coordinate from the Mean Earth/Polar Axis (ME) frame to the Principal Axis (PA) frame
    used by the global LOLA elevation map
    :param lat: ME latitude in degrees (-90 to 90)
    :type lat: float
    :param lon: ME longitude in degrees (any value, wrapped to [0, 360))
    :type lon: float
    :return: PA (longitude, latitude) in degrees, with longitude in (-180, 180]. Note the lon-first order
    :rtype: tuple[float, float]
    """
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
    """
    Function to read a single pixel from an open global raster, wrapping longitude at the seam and clamping the poles
    to the edge rows
    :param raster: Open rasterio dataset of the global map (projected or geographic lon/lat grid)
    :type raster: rasterio.io.DatasetReader
    :param lon: PA longitude in degrees
    :type lon: float
    :param lat: PA latitude in degrees (-90 to 90)
    :type lat: float
    :return: Pixel value with the band's scale and offset applied, or None if the row is outside the raster or the
        pixel is masked or not finite
    :rtype: float | None
    """
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
    """
    Function to read elevation or estimate slope at a lunar coordinate from the global LOLA elevation map.
    Slope comes from central differences of the elevations one pixel east, west, north, and south of the coordinate
    :param lat: ME latitude in degrees (-90 to 90)
    :type lat: float
    :param lon: ME longitude in degrees (-180 to 360)
    :type lon: float
    :param slope: If True return the slope in degrees, otherwise return the elevation in meters
    :type slope: bool
    :return: Elevation in meters or slope in degrees, or None if the map or any needed pixel is unavailable
    :rtype: float | None
    """
    try:
        if not GLOBAL_ELEVATION_MAP.is_file():
            return None

        lon_pa, lat_pa = _moon_me_to_pa(lat, lon)
        with rasterio.open(GLOBAL_ELEVATION_MAP) as raster:
            if not slope:
                return _read_global_pixel(raster, lon_pa, lat_pa)

            samples = []
            for azimuth in (90, 270, 0, 180):
                lon_near, lat_near, _ = GLOBAL_GEOD.fwd(lon_pa, lat_pa, azimuth, GLOBAL_PIXEL_M)
                elevation = _read_global_pixel(raster, lon_near, lat_near)
                if elevation is None:
                    return None
                samples.append(elevation)

            east, west, north, south = samples
            rise = hypot(east - west, north - south)
            return degrees(atan2(rise, 2 * GLOBAL_PIXEL_M))
    except (OSError, RasterioError, ProjError) as e:
        raise TerrainDataUnavailable("[terrain.py] Could not read the global LOLA elevation map!") from e


def get_terrain_elevation(lat: float, lon: float) -> float | None:
    """
    Function to get the terrain elevation at a lunar coordinate, preferring the 80 m/px south pole map and falling
    back to the global map
    :param lat: Latitude in degrees (-90 to 90)
    :type lat: float
    :param lon: Longitude in degrees (-180 to 360)
    :type lon: float
    :return: Elevation in meters, or None if no map has a valid pixel at the coordinate
    :rtype: float | None
    """
    elevation = _sample_terrain_map(ELEVATION_MAP, "elevation", lat, lon)
    if elevation is not None:
        return elevation
    return _read_global_terrain(lat, lon)


def get_ground_angle(lat: float, lon: float) -> float | None:
    """
    Function to get the ground slope at a lunar coordinate, preferring the south pole slope map and falling back to
    an estimate from the global elevation map when the polar value is missing or outside 0 to 90 degrees
    :param lat: Latitude in degrees (-90 to 90)
    :type lat: float
    :param lon: Longitude in degrees (-180 to 360)
    :type lon: float
    :return: Slope in degrees, or None if no map has a valid value at the coordinate
    :rtype: float | None
    """
    angle = _sample_terrain_map(SLOPE_MAP, "slope", lat, lon)
    if angle is not None and 0 <= angle <= 90:
        return angle
    return _read_global_terrain(lat, lon, slope=True)


def get_slope_footprint_p95(
    lat: float,
    lon: float,
    footprint_radius_m: float = DEFAULT_FOOTPRINT_RADIUS_M,
) -> dict[str, float | int] | None:
    """Sample a circular landing footprint and return its 95th-percentile slope.

    The footprint uses the center, eight points at half-radius, and sixteen
    points at the perimeter. If any required slope sample is unavailable, the
    complete footprint is considered unavailable rather than partially safe.
    """
    _validate_coordinates(lat, lon)
    if not isfinite(footprint_radius_m) or footprint_radius_m <= 0:
        raise ValueError("[terrain.py] Footprint radius must be a positive finite number!")

    coordinates = [(lon, lat)]
    for distance_m, count in (
        (footprint_radius_m / 2.0, 8),
        (footprint_radius_m, 16),
    ):
        for index in range(count):
            sample_lon, sample_lat, _ = GLOBAL_GEOD.fwd(
                lon,
                lat,
                index * 360.0 / count,
                distance_m,
            )
            coordinates.append((sample_lon, sample_lat))

    slopes = []
    for sample_lon, sample_lat in coordinates:
        slope = get_ground_angle(sample_lat, sample_lon)
        if slope is None:
            return None
        slopes.append(slope)

    ordered = sorted(slopes)
    rank = 0.95 * (len(ordered) - 1)
    lower_index = floor(rank)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = rank - lower_index
    slope_p95 = (
        ordered[lower_index]
        + fraction * (ordered[upper_index] - ordered[lower_index])
    )

    return {
        "slope_p95_degrees": slope_p95,
        "footprint_radius_m": footprint_radius_m,
        "footprint_diameter_m": footprint_radius_m * 2.0,
        "sample_count": len(slopes),
        "percentile": 95,
    }


def get_lola_roughness_deg(lat: float, lon: float) -> float | None:
    """
    Function to get the terrain roughness at a lunar coordinate from the global LOLA MAS_225M_16 map, which gives the
    median absolute along-track slope at a 225 m baseline (Rosenburg et al., 2011). The map is a raw 16 px/degree
    grid that starts at 90°N, 0°E, so this reads the single cell that contains the coordinate with no interpolation.
    At the poles, where longitude is undefined, it reads column 0
    :param lat: ME latitude in degrees (-90 to 90)
    :type lat: float
    :param lon: ME longitude in degrees (-180 to 360, wrapped to [0, 360))
    :type lon: float
    :return: Median absolute slope in degrees (about 0 to 36.3)
    :rtype: float | None
    """
    _validate_coordinates(lat, lon)

    row = min(floor((90 - lat) * LOLA_ROUGHNESS_PIXELS_PER_DEGREE), LOLA_ROUGHNESS_HEIGHT - 1,)
    col = floor((lon % 360) * LOLA_ROUGHNESS_PIXELS_PER_DEGREE) % LOLA_ROUGHNESS_WIDTH
    if abs(lat) == 90:
        col = 0 #long is undefined at the poles

    try:
        with LOLA_ROUGHNESS_MAP.open("rb") as grid:
            if fstat(grid.fileno()).st_size != LOLA_ROUGHNESS_FILE_SIZE:
                return None

            grid.seek((row * LOLA_ROUGHNESS_WIDTH + col) * LOLA_ROUGHNESS_SAMPLE.size)
            sample = grid.read(LOLA_ROUGHNESS_SAMPLE.size)
    except OSError:
        return None

    if len(sample) != LOLA_ROUGHNESS_SAMPLE.size:
        return None

    (raw,) = LOLA_ROUGHNESS_SAMPLE.unpack(sample)
    if not -30_001 <= raw <= -5_808:
        return None

    #PDS scaling is raw * 0.0015 + 45. Clamp the published minimum to zero
    return max(0.0, (raw + 30_000) * 0.0015)
