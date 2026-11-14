"""Terrain-aware lunar horizon calculations from a LOLA elevation raster."""

from math import atan2, ceil, cos, degrees, floor, isclose, isfinite, sin
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pyproj import CRS, Geod, Transformer
from pyproj.exceptions import ProjError
from rasterio.errors import RasterioError

from app.services.terrain import ELEVATION_MAP, TerrainDataUnavailable


MAX_SAMPLES = 250_000


def _finite(value: float, name: str) -> float:
    """Accept a numeric parameter and its name; return a validated float."""
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
    """Accept a raster and projected location; return elevation in meters or None."""
    row, col = dataset.index(x, y)

    if not (0 <= row < dataset.height and 0 <= col < dataset.width):
        return None

    pixel = next(dataset.sample([(x, y)], indexes=1, masked=True))[0]

    if np.ma.is_masked(pixel):
        return None

    value = float(pixel) * dataset.scales[0] + dataset.offsets[0]

    return value if isfinite(value) else None


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

    if not (-90 <= lat <= 90 and -180 <= lon <= 360):
        raise ValueError("Lunar coordinates are out of range")

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

                xs, ys = projection.transform(longitudes, latitudes, errcheck=True)

                highest_angle = -90.0
                covered = True

                for distance, x, y in zip(distances, xs, ys):
                    elevation = _sample_elevation(dataset, float(x), float(y))

                    if elevation is None:
                        covered = False
                        break

                    central_angle = float(distance) / moon_radius_m
                    target_radius = moon_radius_m + elevation

                    angle = degrees(
                        atan2(
                            target_radius * cos(central_angle) - observer_radius,
                            target_radius * sin(central_angle),
                        )
                    )

                    highest_angle = max(highest_angle, angle)

                profile.append(
                    dict(
                        azimuth_deg=float(azimuth),
                        horizon_elevation_deg=highest_angle if covered else None,
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
