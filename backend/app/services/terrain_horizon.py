"""Terrain-aware lunar horizon calculations from LOLA elevation rasters."""

from math import ceil, floor, isclose, isfinite, pi
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pyproj import CRS, Geod, Transformer
from pyproj.exceptions import ProjError
from rasterio.errors import RasterioError
from rasterio.transform import rowcol
from rasterio.windows import Window

import app.services.terrain as terrain_service
from app.services.terrain import ELEVATION_MAP, TerrainDataUnavailable

# Global 64 ppd equirectangular LOLA DEM used when the regional DEM lacks coverage.
GLOBAL_ELEVATION_MAP: Path = getattr(
    terrain_service,
    "GLOBAL_ELEVATION_MAP",
    ELEVATION_MAP.parent / "LDEM64_PA_eqc_m.tif",
)

# Limit raster sampling work per request to control CPU and I/O costs.
# This is a performance safeguard, not a scientific accuracy threshold.
MAX_SAMPLES = 250_000


def _finite(value: object, name: str) -> float:
    """Validate a numeric input and convert it to a finite float."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc

    if not isfinite(number):
        raise ValueError(f"{name} must be a finite number")

    return number


def _is_global_longitude_raster(
    dataset: Any,
    moon_radius_m: float,
    *,
    is_geographic: bool = False,
) -> bool:
    """Return True if the raster spans 360 degrees of lunar longitude."""
    if dataset.transform.b != 0 or dataset.transform.d != 0:
        return False

    width = abs(dataset.bounds.right - dataset.bounds.left)
    full_circle = 360.0 if is_geographic else 2.0 * pi * moon_radius_m

    return isclose(width, full_circle, rel_tol=1e-4)


def _align_geographic_longitudes(xs: np.ndarray, dataset: Any) -> np.ndarray:
    """Align [-180, 180] longitudes to [0, 360) if the raster uses 0..360 bounds."""
    if dataset.bounds.left >= 0.0 and dataset.bounds.right > 180.0:
        return np.mod(xs, 360.0)
    return xs


def _sample_elevation(
    dataset: Any,
    x: float,
    y: float,
    *,
    wrap_longitude: bool = False,
) -> float | None:
    """Read terrain elevation from a projected or geographic DEM coordinate."""
    row, col = dataset.index(x, y)

    if row == dataset.height and isclose(y, dataset.bounds.bottom, abs_tol=1e-3):
        row = dataset.height - 1

    if wrap_longitude:
        col %= dataset.width

    if not (0 <= row < dataset.height and 0 <= col < dataset.width):
        return None

    window = Window(col_off=col, row_off=row, width=1, height=1)
    pixel = dataset.read(1, window=window, masked=True)[0, 0]

    if np.ma.is_masked(pixel):
        return None

    value = float(pixel) * dataset.scales[0] + dataset.offsets[0]
    return value if isfinite(value) else None


def _read_window_elevations(
    dataset: Any,
    rows: np.ndarray,
    cols: np.ndarray,
    mask: np.ndarray,
    elevations: np.ndarray,
) -> None:
    """Populate elevations for masked indices using a single bounding window."""
    if not np.any(mask):
        return

    sub_rows = rows[mask]
    sub_cols = cols[mask]

    row_min = int(sub_rows.min())
    row_max = int(sub_rows.max())
    col_min = int(sub_cols.min())
    col_max = int(sub_cols.max())

    window = Window(
        col_off=col_min,
        row_off=row_min,
        width=col_max - col_min + 1,
        height=row_max - row_min + 1,
    )

    pixels = dataset.read(1, window=window, masked=True)
    selected = pixels[sub_rows - row_min, sub_cols - col_min]
    scaled = selected.astype(np.float64) * dataset.scales[0] + dataset.offsets[0]
    elevations[mask] = scaled.filled(np.nan)


def _sample_ray_elevations(
    dataset: Any,
    xs: np.ndarray,
    ys: np.ndarray,
    *,
    wrap_longitude: bool = False,
) -> np.ndarray:
    """Read terrain elevations for an entire ray."""
    rows, cols = rowcol(dataset.transform, xs, ys)
    rows = np.asarray(rows, dtype=np.int64)
    cols = np.asarray(cols, dtype=np.int64)

    # Clamp exact South Pole samples landing on the bottom raster edge.
    south_edge = (rows == dataset.height) & np.isclose(
        ys, dataset.bounds.bottom, atol=1e-3
    )
    rows[south_edge] = dataset.height - 1

    if wrap_longitude:
        cols = cols % dataset.width

    elevations = np.full(xs.shape, np.nan, dtype=np.float64)

    inside = (
        (rows >= 0)
        & (rows < dataset.height)
        & (cols >= 0)
        & (cols < dataset.width)
    )

    if not np.any(inside):
        return elevations

    # Split window reads when a ray crosses the antimeridian on a global DEM.
    if wrap_longitude and (
        int(cols[inside].max()) - int(cols[inside].min()) > dataset.width // 2
    ):
        half_width = dataset.width // 2
        _read_window_elevations(
            dataset, rows, cols, inside & (cols < half_width), elevations
        )
        _read_window_elevations(
            dataset, rows, cols, inside & (cols >= half_width), elevations
        )
    else:
        _read_window_elevations(dataset, rows, cols, inside, elevations)

    return elevations


def _compute_terrain_horizon(
    lat: float,
    lon: float,
    *,
    raster_path: Path,
    observer_height_m: float,
    max_distance_m: float,
    azimuth_step_deg: float,
    distance_step_m: float | None,
) -> dict[str, Any]:
    """Compute a terrain-aware horizon profile against a specific DEM file."""
    if not raster_path.is_file():
        raise TerrainDataUnavailable(f"LOLA elevation DEM is missing: {raster_path}")

    ray_count = int(round(360.0 / azimuth_step_deg))

    try:
        with rasterio.open(raster_path) as dataset:
            if dataset.count < 1 or dataset.crs is None:
                raise TerrainDataUnavailable("Expected a lunar elevation DEM with a valid CRS")

            map_crs = CRS.from_wkt(dataset.crs.to_wkt())
            if not map_crs.axis_info:
                raise TerrainDataUnavailable("DEM CRS has no axis unit metadata")

            unit_factor = map_crs.axis_info[0].unit_conversion_factor
            is_geographic = map_crs.is_geographic

            if map_crs.is_projected:
                if not isclose(unit_factor, 1.0, abs_tol=1e-9):
                    raise TerrainDataUnavailable("Projected DEM units must be meters")
            elif is_geographic:
                if not isclose(unit_factor, pi / 180.0, rel_tol=1e-6):
                    raise TerrainDataUnavailable("Geographic DEM units must be degrees")
            else:
                raise TerrainDataUnavailable(
                    "Expected a projected or geographic lunar elevation DEM"
                )

            if map_crs.ellipsoid is None:
                raise TerrainDataUnavailable("DEM has no valid lunar reference ellipsoid")

            moon_radius_m = map_crs.ellipsoid.semi_major_metre

            if not isfinite(moon_radius_m) or moon_radius_m <= 0:
                raise TerrainDataUnavailable("DEM has no valid lunar reference radius")

            if not isclose(
                map_crs.ellipsoid.semi_minor_metre, moon_radius_m, rel_tol=1e-9
            ):
                raise TerrainDataUnavailable("A spherical lunar DEM is required")

            res_scale_m = unit_factor * moon_radius_m if is_geographic else 1.0
            res_m = [abs(dataset.res[0]) * res_scale_m, abs(dataset.res[1]) * res_scale_m]

            spacing = (
                min(res_m)
                if distance_step_m is None
                else _finite(distance_step_m, "distance_step_m")
            )

            if spacing <= 0 or spacing > max_distance_m:
                raise ValueError("distance_step_m must be in (0, max_distance_m]")

            if ceil(max_distance_m / spacing) * ray_count > MAX_SAMPLES:
                raise ValueError("Too many ray samples; increase distance/azimuth step")

            wrap_longitude = _is_global_longitude_raster(
                dataset,
                moon_radius_m,
                is_geographic=is_geographic,
            )

            distances = np.arange(spacing, max_distance_m, spacing)
            distances = np.append(distances, max_distance_m)

            projection = Transformer.from_crs(
                map_crs.geodetic_crs, map_crs, always_xy=True
            )

            norm_lon = 0.0 if abs(lat) == 90 else (lon + 180.0) % 360.0 - 180.0
            origin_x, origin_y = projection.transform(
                norm_lon,
                lat,
                errcheck=True,
            )
            if is_geographic:
                origin_x = float(_align_geographic_longitudes(np.asarray(origin_x), dataset))

            origin_elevation = _sample_elevation(
                dataset,
                origin_x,
                origin_y,
                wrap_longitude=wrap_longitude,
            )

            if origin_elevation is None:
                raise TerrainDataUnavailable("Observer position has no valid DEM height")

            geodesic = Geod(a=moon_radius_m, b=moon_radius_m)
            observer_radius = moon_radius_m + origin_elevation + observer_height_m
            azimuths = np.arange(ray_count, dtype=float) * azimuth_step_deg
            profile = []

            for azimuth in azimuths:
                longitudes, latitudes, _ = geodesic.fwd(
                    np.full(len(distances), norm_lon),
                    np.full(len(distances), lat),
                    np.full(len(distances), azimuth),
                    distances,
                )

                xs, ys = projection.transform(
                    longitudes,
                    latitudes,
                    errcheck=True,
                )
                xs_arr = np.asarray(xs)
                if is_geographic:
                    xs_arr = _align_geographic_longitudes(xs_arr, dataset)

                elevations = _sample_ray_elevations(
                    dataset,
                    xs_arr,
                    np.asarray(ys),
                    wrap_longitude=wrap_longitude,
                )

                # Stop at the first missing pixel to preserve continuous coverage.
                gaps = np.flatnonzero(~np.isfinite(elevations))
                prefix_len = int(gaps[0]) if len(gaps) else len(distances)
                covered_distances = distances[:prefix_len]

                if prefix_len:
                    central_angles = covered_distances / moon_radius_m
                    target_radii = moon_radius_m + elevations[:prefix_len]

                    angles = np.degrees(
                        np.arctan2(
                            target_radii * np.cos(central_angles) - observer_radius,
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
                        horizon_elevation_deg=horizon_angle if complete else None,
                        partial_horizon_elevation_deg=(
                            horizon_angle if not complete else None
                        ),
                        covered_distance_m=(
                            float(covered_distances[-1]) if prefix_len else 0.0
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
                    dem_resolution_m=res_m,
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

    Uses the high-resolution regional DEM (ELEVATION_MAP) when it provides full
    coverage, and automatically falls back to the global LDEM64_PA_eqc_m.tif
    DEM for off-pole coordinates or incomplete edge coverage.
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

    if dem_path is not None:
        return _compute_terrain_horizon(
            lat,
            lon,
            raster_path=Path(dem_path),
            observer_height_m=observer_height_m,
            max_distance_m=max_distance_m,
            azimuth_step_deg=azimuth_step_deg,
            distance_step_m=distance_step_m,
        )

    candidates: list[Path] = [ELEVATION_MAP]
    if GLOBAL_ELEVATION_MAP != ELEVATION_MAP and GLOBAL_ELEVATION_MAP.is_file():
        candidates.append(GLOBAL_ELEVATION_MAP)

    best_result: dict[str, Any] | None = None
    last_error: TerrainDataUnavailable | None = None

    for candidate in candidates:
        try:
            result = _compute_terrain_horizon(
                lat,
                lon,
                raster_path=candidate,
                observer_height_m=observer_height_m,
                max_distance_m=max_distance_m,
                azimuth_step_deg=azimuth_step_deg,
                distance_step_m=distance_step_m,
            )
        except TerrainDataUnavailable as exc:
            last_error = exc
            continue

        if result["data_quality"] == "complete_within_radius":
            return result

        if (
            best_result is None
            or result["valid_azimuths"] > best_result["valid_azimuths"]
        ):
            best_result = result

    if best_result is not None:
        return best_result

    assert last_error is not None
    raise last_error


def is_body_visible(
    horizon: dict[str, Any],
    body_azimuth_deg: float,
    body_elevation_deg: float,
) -> bool | None:
    """Accept a horizon and body's azimuth/elevation; return visibility or None."""
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