"""Integration tests for scoring in the site-data response."""

import pytest

from app import routes


def _patch_site_services(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "get_lola_roughness_deg", lambda lat, lon: 2.5)
    monkeypatch.setattr(routes, "get_terrain_elevation", lambda lat, lon: 120.0)
    monkeypatch.setattr(routes, "get_ground_angle", lambda lat, lon: 3.0)
    monkeypatch.setattr(
        routes,
        "get_average_sun_angle",
        lambda lat, lon: {
            "avg_daytime_sun_angle": 12.0,
            "sunlight_fraction": 0.8,
            "longest_darkness_hours": 8.0,
            "period_start": "2026-11-01",
            "period_stop": "2026-11-30 12:44",
            "time_step_hours": 2.0,
        },
    )
    monkeypatch.setattr(
        routes,
        "get_earth_visibility_window",
        lambda lat, lon: {
            "windows": [],
            "earth_visibility_fraction": 0.45,
            "longest_earth_blackout_hours": 120.0,
        },
    )
    monkeypatch.setattr(
        routes,
        "get_slope_footprint_p95",
        lambda lat, lon, radius: {
            "slope_p95_degrees": 4.0,
            "sample_count": 25,
        },
    )


def test_fetch_data_returns_score_and_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_site_services(monkeypatch)

    response = routes.fetch_data(10.0, 20.0, None, 250.0)

    assert response.score == pytest.approx(67.60, abs=0.01)
    assert response.scoring.score == response.score
    assert response.scoring.data_quality == "complete"
    assert response.scoring_metrics["slope_p95_degrees"] == 4.0
    assert response.scoring.metadata["footprint_radius_m"] == 250.0
    assert response.scoring.metadata["slope_sample_count"] == 25


def test_fetch_data_reports_insufficient_scoring_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_site_services(monkeypatch)
    monkeypatch.setattr(routes, "get_average_sun_angle", lambda lat, lon: None)

    response = routes.fetch_data(10.0, 20.0, None, 250.0)

    assert response.score is None
    assert response.scoring.data_quality == "insufficient_data"
    assert response.scoring.unavailable_sources == ["solar_ephemeris"]
    assert response.scoring.missing_metrics == [
        "sunlight_fraction",
        "longest_darkness_hours",
    ]
