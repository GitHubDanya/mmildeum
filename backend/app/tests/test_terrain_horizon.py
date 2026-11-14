"""Unit tests for local terrain horizons using synthetic lunar DEMs."""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from pyproj import CRS, Geod, Transformer
from rasterio.transform import from_origin

from app.services.terrain import TerrainDataUnavailable
from app.services.terrain_horizon import get_terrain_horizon, is_body_visible

# NoData sentinel, distinct from all generated synthetic terrain elevations.
NODATA = -9999.0

MOON_CRS = (
    "+proj=stere +lat_0=-90 +lon_0=0 +lat_ts=-90 "
    "+a=1737400 +b=1737400 +units=m +no_defs +type=crs"
)

LAT = -89.5
LON = 0.0


def make_dem(tmp_path: Path, *, ridge: bool = False, gap: bool = False) -> Path:
    """Accept a temporary directory and terrain flags; return a DEM file path."""
    crs = CRS.from_user_input(MOON_CRS)
    # Enforce longitude-latitude input order regardless of CRS axis definitions.
    projection = Transformer.from_crs(crs.geodetic_crs, crs, always_xy=True)
    x0, y0 = projection.transform(LON, LAT)

    transform = from_origin(x0 - 1050, y0 + 1050, 100, 100)
    data = np.zeros((21, 21), dtype=np.float32)

    if ridge or gap:
        geod = Geod(a=1737400, b=1737400)
        ridge_lon, ridge_lat, _ = geod.fwd(LON, LAT, 0, 300)

        x, y = projection.transform(ridge_lon, ridge_lat)
        row, col = rasterio.transform.rowcol(transform, x, y)

        data[row, col] = NODATA if gap else 250.0

    path = tmp_path / "synthetic_lunar_dem.tif"

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=21,
        width=21,
        count=1,
        dtype="float32",
        crs=crs.to_wkt(),
        transform=transform,
        nodata=-9999,
    ) as dataset:
        dataset.write(data, 1)

    return path


def test_flat_terrain_is_unobstructed(tmp_path: Path) -> None:
    """Accept a temporary directory; verify flat terrain visibility; return None."""
    result = get_terrain_horizon(
        LAT,
        LON,
        dem_path=make_dem(tmp_path),
        azimuth_step_deg=90,
        distance_step_m=100,
        max_distance_m=500,
    )

    assert result["data_quality"] == "complete_within_radius"
    assert len(result["profile"]) == 4
    assert is_body_visible(result, 0, 5) is True
    assert is_body_visible(result, 359, 5) is True


def test_ridge_blocks_view_and_height_changes(tmp_path: Path) -> None:
    """Accept a temporary directory; verify a ridge and observer height; return None."""
    path = make_dem(tmp_path, ridge=True)

    settings = dict(
        dem_path=path,
        azimuth_step_deg=90,
        distance_step_m=100,
        max_distance_m=500,
    )

    low = get_terrain_horizon(LAT, LON, observer_height_m=2, **settings)
    high = get_terrain_horizon(LAT, LON, observer_height_m=100, **settings)

    assert low["profile"][0]["horizon_elevation_deg"] > 10

    assert (
        high["profile"][0]["horizon_elevation_deg"]
        < low["profile"][0]["horizon_elevation_deg"]
    )

    assert is_body_visible(low, 0, 5) is False
    assert is_body_visible(low, 90, 5) is True


def test_missing_pixels_are_not_guessed(tmp_path: Path) -> None:
    """Accept a temporary directory; verify missing DEM handling; return None."""
    result = get_terrain_horizon(
        LAT,
        LON,
        dem_path=make_dem(tmp_path, gap=True),
        azimuth_step_deg=90,
        distance_step_m=100,
        max_distance_m=500,
    )

    assert result["data_quality"] == "insufficient_data"
    assert result["profile"][0]["horizon_elevation_deg"] is None
    assert is_body_visible(result, 0, 5) is None
    assert is_body_visible(result, 90, 5) is True


def test_missing_dem_raises(tmp_path: Path) -> None:
    """Accept a temporary directory; verify missing file errors; return None."""
    with pytest.raises(TerrainDataUnavailable):
        get_terrain_horizon(LAT, LON, dem_path=tmp_path / "absent.tif")


def test_invalid_step_raises(tmp_path: Path) -> None:
    """Accept a temporary directory; verify angle-step validation; return None."""
    with pytest.raises(ValueError):
        get_terrain_horizon(
            LAT,
            LON,
            dem_path=make_dem(tmp_path),
            azimuth_step_deg=7,
        )


def test_interpolation_and_azimuth_wraparound() -> None:
    """Accept no arguments; verify circular azimuth interpolation; return None."""
    horizon = dict(
        profile=[
            dict(azimuth_deg=0.0, horizon_elevation_deg=10.0),
            dict(azimuth_deg=90.0, horizon_elevation_deg=0.0),
            dict(azimuth_deg=180.0, horizon_elevation_deg=0.0),
            dict(azimuth_deg=270.0, horizon_elevation_deg=0.0),
        ],
        metadata=dict(azimuth_step_deg=90.0),
    )

    assert is_body_visible(horizon, 45, 6) is True
    assert is_body_visible(horizon, 45, 4) is False
    assert is_body_visible(horizon, 315, 4) is False
    assert is_body_visible(horizon, 315, 6) is True
