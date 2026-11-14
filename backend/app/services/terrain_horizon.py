"""Terrain-aware lunar horizon calculations from a LOLA elevation raster."""

from math import ceil, floor, isclose, isfinite
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pyproj import CRS, Geod, Transformer
from pyproj.exceptions import ProjError
from rasterio.errors import RasterioError
from rasterio.transform import rowcol
from rasterio.windows import Window

from app.services.terrain import ELEVATION_MAP, TerrainDataUnavailable

# Limit raster sampling work per request to control CPU and I/O costs.
# This is a performance safeguard, not a scientific accuracy threshold.
MAX_SAMPLES = 250_000


def _finite(value: object, name: str) -> float:
    """Validate a numeric input and convert it to a finite float.

    Args:
        value: Numeric input value to validate.
        name: Parameter name used in error messages.

    Returns:
        The validated finite floating-point number.

    Raises:
        ValueError: If the value is not numeric, is a boolean,
            is infinite, or is NaN.
    """
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc

    if not isfinite(number):
        raise ValueError(f"{name} must be a finite number")

    return number



def _sample_elevation(dataset: Any, x: float, y: float) -> float | None:
    """Read terrain elevation from a projected DEM coordinate.

    Args:
        dataset: Open Rasterio dataset containing elevation data.
        x: X coordinate in the DEM coordinate reference system.
        y: Y coordinate in the DEM coordinate reference system.

    Returns:
        Terrain elevation in meters, or None if the coordinate
        is outside the raster or contains invalid or missing data.
    """
    # Convert projected coordinates into raster row and column indices.
    row, col = dataset.index(x, y)

    # Check raster bounds before accessing the pixel.
    if not (0 <= row < dataset.height and 0 <= col < dataset.width):
        return None

    # Read the pixel while preserving the raster's NoData mask.
    pixel = next(dataset.sample([(x, y)], indexes=1, masked=True))[0]

    if np.ma.is_masked(pixel):
        return None

    # Apply the raster scale and offset to obtain physical elevation.
    value = float(pixel) * dataset.scales[0] + dataset.offsets[0]

    return value if isfinite(value) else None


def _sample_ray_elevations(
    dataset: Any,
    xs: np.ndarray,
    ys: np.ndarray,
) -> np.ndarray:
    """Read terrain elevations for an entire ray.

    Args:
        dataset: Open Rasterio elevation dataset.
        xs: Projected X coordinates along the ray.
        ys: Projected Y coordinates along the ray.

    Returns:
        Array of elevations in meters.
        Missing or out-of-bounds pixels are represented by NaN.
    """
    # Calculate pixel indices for all positions at once.
    rows, cols = rowcol(dataset.transform, xs, ys)

    rows = np.asarray(rows, dtype=np.int64)
    cols = np.asarray(cols, dtype=np.int64)

    elevations = np.full(xs.shape, np.nan, dtype=np.float64)

    # Identify positions inside the DEM coverage.
    inside = (
        (rows >= 0)
        & (rows < dataset.height)
        & (cols >= 0)
        & (cols < dataset.width)
    )

    if not np.any(inside):
        return elevations

    row_min = int(rows[inside].min())
    row_max = int(rows[inside].max())
    col_min = int(cols[inside].min())
    col_max = int(cols[inside].max())

    # Read one raster window containing all valid positions.
    window = Window(
        col_off=col_min,
        row_off=row_min,
        width=col_max - col_min + 1,
        height=row_max - row_min + 1,
    )

    pixels = dataset.read(
        1,
        window=window,
        masked=True,
    )

    # Extract the requested pixels from the loaded window.
    selected = pixels[
        rows[inside] - row_min,
        cols[inside] - col_min,
    ]

    # Convert stored pixel values into physical elevations.
    scaled = (
        selected.astype(np.float64) * dataset.scales[0]
        + dataset.offsets[0]
    )

    elevations[inside] = scaled.filled(np.nan)

    return elevations




def get_terrain_horizon(
    lat: float,
    lon: float,
    *,
    dem_path: str | Path | None = None,
    observer_height_m: float = 2.0,
    max_distance_m: float = 30_000.0,
    azimuth_step_deg: float = 5.0,
    distance_step_m: float | None = None,
) -> dict[str, Any]:
    """Calculate a sampled, terrain-aware horizon around a lunar observer.

    Args:
        lat: Selenographic latitude in degrees.
        lon: East-positive selenographic longitude in degrees.
        dem_path: Projected LOLA elevation GeoTIFF (defaults to ELEVATION_MAP).
        observer_height_m: Instrument height above local terrain, in meters.
        max_distance_m: Maximum terrain search distance along each azimuth.
        azimuth_step_deg: Angular spacing; must divide 360 exactly.
        distance_step_m: Ray sampling interval; defaults to DEM pixel size.

    Returns:
        Horizon profile with azimuths, angles, coverage status and metadata.
        Missing pixels yield None for affected azimuths; no guessing occurs.

    Raises:
        ValueError: For invalid parameters.
        TerrainDataUnavailable: If the elevation raster or observer is missing.
    """
    lat = _finite(lat, "lat")
    lon = _finite(lon, "lon")
    observer_height_m = _finite(observer_height_m, "observer_height_m")
    max_distance_m = _finite(max_distance_m, "max_distance_m")
    azimuth_step_deg = _finite(azimuth_step_deg, "azimuth_step_deg")

    if not -90 <= lat <= 90:
        raise ValueError("Latitude must be between -90 and 90 degrees")

    if not -180 <= lon <= 360:
        raise ValueError("Longitude must be between -180 and 360 degrees")

    if observer_height_m < 0 or max_distance_m <= 0:
        raise ValueError("Observer height must be nonnegative and radius positive")

    count = 360 / azimuth_step_deg if azimuth_step_deg > 0 else 0

    if not (1 <= count <= 3600 and isclose(count, round(count), abs_tol=1e-8)):
        raise ValueError("azimuth_step_deg must divide 360 with at most 3600 rays")

    raster_path = Path(dem_path) if dem_path is not None else ELEVATION_MAP

    if not raster_path.is_file():
        raise TerrainDataUnavailable(f"LOLA elevation DEM is missing: {raster_path}")

    try:
        with rasterio.open(raster_path) as dataset:
            if dataset.count < 1 or dataset.crs is None or not dataset.crs.is_projected:
                raise TerrainDataUnavailable("Expected a projected lunar elevation DEM")

            map_crs = CRS.from_wkt(dataset.crs.to_wkt())
            unit_factor = map_crs.axis_info[0].unit_conversion_factor

            if not isclose(unit_factor, 1.0, abs_tol=1e-9):
                raise TerrainDataUnavailable("DEM projection units must be meters")

            moon_radius_m = map_crs.ellipsoid.semi_major_metre

            if not isfinite(moon_radius_m) or moon_radius_m <= 0:
                raise TerrainDataUnavailable("DEM has no valid lunar reference radius")

            if not isclose(map_crs.ellipsoid.semi_minor_metre, moon_radius_m, rel_tol=1e-9):
                raise TerrainDataUnavailable("A spherical lunar DEM is required")

            spacing = (
                min(abs(dataset.res[0]), abs(dataset.res[1]))
                if distance_step_m is None
                else _finite(distance_step_m, "distance_step_m")
            )

            if spacing <= 0 or spacing > max_distance_m:
                raise ValueError("distance_step_m must be in (0, max_distance_m]")

            ray_count = int(round(count))

            if ceil(max_distance_m / spacing) * ray_count > MAX_SAMPLES:
                raise ValueError("Too many ray samples; increase distance/azimuth step")

            distances = np.arange(spacing, max_distance_m, spacing)
            distances = np.append(distances, max_distance_m)

            projection = Transformer.from_crs(
                map_crs.geodetic_crs, map_crs, always_xy=True
            )

            origin_x, origin_y = projection.transform(
                0.0 if abs(lat) == 90 else (lon + 180) % 360 - 180,
                lat,
                errcheck=True,
            )

            origin_elevation = _sample_elevation(dataset, origin_x, origin_y)

            if origin_elevation is None:
                raise TerrainDataUnavailable("Observer position has no valid DEM height")

            geodesic = Geod(a=moon_radius_m, b=moon_radius_m)
            observer_radius = moon_radius_m + origin_elevation + observer_height_m
            azimuths = np.arange(ray_count, dtype=float) * azimuth_step_deg
            profile = []

            
            for azimuth in azimuths:
                longitudes, latitudes, _ = geodesic.fwd(
                    np.full(len(distances), lon),
                    np.full(len(distances), lat),
                    np.full(len(distances), azimuth),
                    distances,
                )

                xs, ys = projection.transform(
                    longitudes,
                    latitudes,
                    errcheck=True,
                )

                elevations = _sample_ray_elevations(
                    dataset,
                    np.asarray(xs),
                    np.asarray(ys),
                )

                # Stop at the first missing pixel to preserve continuous coverage.
                gaps = np.flatnonzero(~np.isfinite(elevations))

                prefix_len = (
                    int(gaps[0])
                    if len(gaps)
                    else len(distances)
                )

                covered_distances = distances[:prefix_len]

                if prefix_len:
                    central_angles = covered_distances / moon_radius_m

                    target_radii = (
                        moon_radius_m + elevations[:prefix_len]
                    )

                    angles = np.degrees(
                        np.arctan2(
                            target_radii * np.cos(central_angles)
                            - observer_radius,
                            target_radii * np.sin(central_angles),
                        )
                    )

                    horizon_angle = float(angles.max())
                else:
                    horizon_angle = None

                complete = prefix_len == len(distances)

                profile.append(
                    dict(
                        azimuth_deg=float(azimuth),
                        horizon_elevation_deg=(
                            horizon_angle if complete else None
                        ),
                        partial_horizon_elevation_deg=(
                            horizon_angle if not complete else None
                        ),
                        covered_distance_m=(
                            float(covered_distances[-1])
                            if prefix_len
                            else 0.0
                        ),
                    )
                )

            valid = sum(item["horizon_elevation_deg"] is not None for item in profile)

            return dict(
                latitude=lat,
                longitude=lon,
                profile=profile,
                data_quality=(
                    "complete_within_radius"
                    if valid == ray_count
                    else "insufficient_data"
                ),
                valid_azimuths=valid,
                total_azimuths=ray_count,
                metadata=dict(
                    dem_source=raster_path.name,
                    dem_resolution_m=list(dataset.res),
                    moon_radius_m=moon_radius_m,
                    observer_height_m=observer_height_m,
                    max_distance_m=max_distance_m,
                    distance_step_m=spacing,
                    azimuth_step_deg=azimuth_step_deg,
                    visibility_limit="Only tested within the configured radius",
                ),
            )

    except (RasterioError, OSError, ProjError) as exc:
        raise TerrainDataUnavailable("Could not read or project the lunar DEM") from exc


def is_body_visible(
    horizon: dict[str, Any],
    body_azimuth_deg: float,
    body_elevation_deg: float,
) -> bool | None:
    """Accept a horizon and body's azimuth/elevation; return visibility or None.

    Interpolates between neighboring azimuths, including the 360/0 boundary.
    Returns None if either neighboring horizon sample lacks coverage.
    """
    azimuth = _finite(body_azimuth_deg, "body_azimuth_deg") % 360.0
    elevation = _finite(body_elevation_deg, "body_elevation_deg")

    if not -90 <= elevation <= 90:
        raise ValueError("body_elevation_deg must be between -90 and 90")

    profile = horizon["profile"]
    step = horizon["metadata"]["azimuth_step_deg"]

    raw_index = azimuth / step
    index = int(floor(raw_index)) % len(profile)
    fraction = raw_index - floor(raw_index)
    next_index = (index + 1) % len(profile)

    first = profile[index]["horizon_elevation_deg"]
    second = profile[next_index]["horizon_elevation_deg"]

    if first is None or (fraction > 1e-10 and second is None):
        return None

    if fraction <= 1e-10:
        return elevation > first

    terrain_angle = first + (second - first) * fraction

    return elevation > terrain_angle
