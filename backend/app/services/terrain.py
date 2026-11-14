"""LOLA terrain lookups (roughness class, elevation, slope, and roughness) at lunar coordinates."""

from dataclasses import dataclass
from functools import cache
from math import asin, atan2, cos, degrees, floor, hypot, isclose, isfinite, radians, sin, sqrt
from pathlib import Path

import numpy as np
import rasterio
from numpy.ma import is_masked
from pyproj import CRS, Geod, Transformer
from pyproj.exceptions import ProjError
from rasterio.crs import CRS as RasterCRS
from rasterio.errors import RasterioError
from rasterio.io import DatasetReader
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
    :return: Polar class ID, or None if the map or a valid pixel is unavailable
    :rtype: int | None
    """
    if not _in_south_pole_coverage(lat, lon) or not TERRAIN_MAP.is_file():
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


ROUGHNESS_WINDOW_M = 2_000


@dataclass(frozen=True)
class TerrainRoughness:
    value_m: float
    dataset: str
    resolution_deg: tuple[float, float]
    window_size_m: int
    valid_sample_count: int
    sample_count: int


def _roughness_windows(raster: DatasetReader, lon: float, lat: float):
    """
    Function to yield the raster windows that cover the circle enclosing the roughness square centered on a
    coordinate. The windows span every column when that circle reaches a pole, and are split in two when they
    cross the longitude seam
    :param raster: Open rasterio dataset of the global map (north-up lon/lat grid spanning 360 degrees)
    :type raster: DatasetReader
    :param lon: PA longitude in degrees
    :type lon: float
    :param lat: PA latitude in degrees (-90 to 90)
    :type lat: float
    :return: One or two non-overlapping windows, or none if no raster rows overlap the circle
    :rtype: Iterator[Window]
    """
    transform = raster.transform
    if (raster.crs is None or not raster.crs.is_geographic or transform.b != 0 or transform.d != 0 or transform.a <= 0 or transform.e >= 0 or not isclose(raster.bounds.right - raster.bounds.left, 360)):
        raise TerrainDataUnavailable("The global roughness DEM must use a north-up longitude/latitude grid.")

    half_width = ROUGHNESS_WINDOW_M / 2
    cap_radius = sqrt(2) * half_width / MOON_RADIUS_M
    latitude_span = degrees(cap_radius)
    row_start = max(0, floor((lat + latitude_span - transform.f) / transform.e))
    row_stop = min(raster.height, floor((lat - latitude_span - transform.f) / transform.e) + 1)
    if row_stop <= row_start:
        return

    if abs(lat) + latitude_span >= 90:
        yield Window(0, row_start, raster.width, row_stop - row_start)
        return

    longitude_span = degrees(asin(sin(cap_radius) / cos(radians(lat))))
    center = (lon - transform.c) % 360
    first = floor((center - longitude_span) / transform.a)
    last = floor((center + longitude_span) / transform.a)
    width = min(last - first + 1, raster.width)
    first %= raster.width

    # Split a window that crosses the longitude seam without repeating cells.
    width_before_seam = min(width, raster.width - first)
    yield Window(first, row_start, width_before_seam, row_stop - row_start)
    if width_before_seam < width:
        yield Window(0, row_start, width - width_before_seam, row_stop - row_start)


def _estimate_global_roughness(raster: DatasetReader, lon: float, lat: float, dataset: str) -> TerrainRoughness | None:
    """
    Function to estimate terrain roughness over a ROUGHNESS_WINDOW_M square centered on a coordinate. The square is
    aligned east/north. The function fits an area-weighted plane to the elevations inside it and reports the
    weighted RMS of the residuals, so a uniform slope does not count as roughness
    :param raster: Open rasterio dataset of the global map (north-up lon/lat grid spanning 360 degrees)
    :type raster: DatasetReader
    :param lon: PA longitude in degrees
    :type lon: float
    :param lat: PA latitude in degrees (-90 to 90)
    :type lat: float
    :param dataset: Dataset name stored in the result
    :type dataset: str
    :return: Roughness estimate, or None if fewer than 4 valid pixels fall in the square or they cannot define a plane
    """
    transform = raster.transform
    half_width = ROUGHNESS_WINDOW_M / 2
    elevations = []
    positions = []
    area_weights = []
    sample_count = 0

    for window in _roughness_windows(raster, lon, lat):
        columns = transform.c + transform.a * (window.col_off + np.arange(window.width) + 0.5)
        rows = transform.f + transform.e * (window.row_off + np.arange(window.height) + 0.5)
        cell_lon, cell_lat = np.meshgrid(columns, rows)
        azimuth, _, distance = GLOBAL_GEOD.inv(np.full_like(cell_lon, lon), np.full_like(cell_lat, lat), cell_lon, cell_lat)
        angle = np.radians(azimuth)
        east = distance * np.sin(angle)
        north = distance * np.cos(angle)
        inside = (abs(east) <= half_width) & (abs(north) <= half_width)
        sample_count += int(np.count_nonzero(inside))

        pixels = raster.read(1, window=window, masked=True).astype(np.float64)
        values = pixels.filled(np.nan) * raster.scales[0] + raster.offsets[0]
        valid = inside & np.isfinite(values)
        elevations.append(values[valid])
        positions.append(np.column_stack((east[valid], north[valid])))
        # Equal angular pixels represent less surface area closer to the poles.
        area_weights.append(np.cos(np.radians(cell_lat[valid])))

    if not elevations:
        return None

    heights = np.concatenate(elevations)
    if heights.size < 4:
        return None

    positions_m = np.concatenate(positions)
    design = np.column_stack((positions_m / half_width, np.ones(heights.size)))
    weights = np.concatenate(area_weights)
    weighted = np.sqrt(weights)
    plane, _, rank, _ = np.linalg.lstsq(design * weighted[:, None], heights * weighted, rcond=None)
    if rank < 3:
        return None

    residuals = heights - design @ plane
    return TerrainRoughness(value_m=float(np.sqrt(np.average(residuals**2, weights=weights))), dataset=dataset, resolution_deg=raster.res, window_size_m=ROUGHNESS_WINDOW_M, valid_sample_count=int(heights.size), sample_count=sample_count,)


def get_terrain_roughness(lat: float, lon: float) -> TerrainRoughness | None:
    """
    Function to get the terrain roughness at a lunar coordinate from the global LOLA elevation map
    :param lat: ME latitude in degrees (-90 to 90)
    :type lat: float
    :param lon: ME longitude in degrees (-180 to 360)
    :type lon: float
    :return: Roughness estimate, or None if the map is missing or has too few valid pixels around the coordinate
    :rtype: TerrainRoughness | None
    """
    _validate_coordinates(lat, lon)
    if not GLOBAL_ELEVATION_MAP.is_file():
        return None
    lon_pa, lat_pa = _moon_me_to_pa(lat, lon)
    try:
        with rasterio.open(GLOBAL_ELEVATION_MAP) as raster:
            return _estimate_global_roughness(raster, lon_pa, lat_pa, GLOBAL_ELEVATION_MAP.name)
    except (OSError, RasterioError, ProjError, np.linalg.LinAlgError) as e:
        raise TerrainDataUnavailable("[terrain.py] Could not estimate roughness from the global LOLA elevation map!") from e
