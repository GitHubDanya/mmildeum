"""Tests for landing-footprint slope aggregation."""

import pytest

from app.services import terrain


def test_slope_footprint_returns_interpolated_p95(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slopes = iter(float(value) for value in range(25))
    monkeypatch.setattr(terrain, "get_ground_angle", lambda lat, lon: next(slopes))

    result = terrain.get_slope_footprint_p95(0.0, 0.0, 250.0)

    assert result is not None
    assert result["slope_p95_degrees"] == pytest.approx(22.8)
    assert result["sample_count"] == 25
    assert result["footprint_radius_m"] == 250.0


def test_slope_footprint_requires_every_sample(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(terrain, "get_ground_angle", lambda lat, lon: None)

    assert terrain.get_slope_footprint_p95(0.0, 0.0, 250.0) is None


@pytest.mark.parametrize("radius", [0, -1, float("inf")])
def test_slope_footprint_rejects_invalid_radius(radius: float) -> None:
    with pytest.raises(ValueError):
        terrain.get_slope_footprint_p95(0.0, 0.0, radius)
