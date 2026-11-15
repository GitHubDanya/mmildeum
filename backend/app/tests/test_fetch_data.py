"""Integration tests for unified mission evaluation and scoring."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import routes


START = datetime(2026, 11, 15, tzinfo=timezone.utc)
END = START + timedelta(hours=24)


def _patch_site_services(monkeypatch: pytest.MonkeyPatch) -> dict:
    horizon = {"profile": [], "data_quality": "complete_within_radius"}
    monkeypatch.setattr(routes, "get_terrain_horizon", Mock(return_value=horizon))
    monkeypatch.setattr(routes, "get_lola_roughness_deg", lambda lat, lon: 2.5)
    monkeypatch.setattr(routes, "get_terrain_elevation", lambda lat, lon: 120.0)
    monkeypatch.setattr(routes, "get_ground_angle", lambda lat, lon: 3.0)
    monkeypatch.setattr(
        routes,
        "get_slope_footprint_p95",
        lambda lat, lon, radius: {
            "slope_p95_degrees": 4.0,
            "sample_count": 25,
        },
    )
    monkeypatch.setattr(
        routes,
        "get_average_duration_of_sunlight",
        Mock(
            return_value={
                "sunlight_fraction": 0.8,
                "longest_darkness_hours": 8.0,
                "sunlight_windows": [
                    {
                        "start": START.isoformat(),
                        "end": (START + timedelta(hours=16)).isoformat(),
                    }
                ],
            }
        ),
    )
    monkeypatch.setattr(
        routes,
        "get_earth_visibility_window",
        Mock(
            return_value={
                "windows": [],
                "earth_visibility_fraction": 0.45,
                "longest_earth_blackout_hours": 120.0,
            }
        ),
    )
    return horizon


def test_fetch_data_returns_score_and_shared_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    horizon = _patch_site_services(monkeypatch)

    response = routes.fetch_data(
        10.0,
        20.0,
        START,
        END,
        60,
        250.0,
    )

    assert response.score == pytest.approx(67.60, abs=0.01)
    assert response.scoring.score == response.score
    assert response.scoring.data_quality == "complete"
    assert response.scoring_metrics["slope_p95_degrees"] == 4.0
    assert response.mission_start == START
    assert response.mission_end == END
    assert response.step_minutes == 60
    assert response.scoring.metadata["sample_count"] == 24
    assert response.scoring.metadata["footprint_radius_m"] == 250.0
    assert response.scoring.metadata["slope_sample_count"] == 25

    routes.get_average_duration_of_sunlight.assert_called_once_with(
        10.0,
        20.0,
        START,
        END,
        step_minutes=60,
        horizon_data=horizon,
    )
    routes.get_earth_visibility_window.assert_called_once_with(
        10.0,
        20.0,
        START,
        END,
        step_minutes=60,
        horizon_data=horizon,
    )


def test_fetch_data_reports_unavailable_solar_ephemeris(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_site_services(monkeypatch)
    monkeypatch.setattr(
        routes,
        "get_average_duration_of_sunlight",
        Mock(side_effect=routes.SunlightDataUnavailable("offline")),
    )

    response = routes.fetch_data(
        10.0,
        20.0,
        START,
        END,
        60,
        250.0,
    )

    assert response.score is None
    assert response.scoring.data_quality == "insufficient_data"
    assert response.scoring.unavailable_sources == ["solar_ephemeris"]
    assert response.scoring.missing_metrics == [
        "sunlight_fraction",
        "longest_darkness_hours",
    ]


def test_fetch_data_requires_timezone_aware_mission_bounds() -> None:
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)

    response = client.get(
        "/api/fetch-data",
        params={
            "lat": 10,
            "long": 20,
            "mission_start": "2026-11-15T00:00:00",
            "mission_end": "2026-11-16T00:00:00",
        },
    )

    assert response.status_code == 422


def test_fetch_data_accepts_requested_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_site_services(monkeypatch)
    app = FastAPI()
    app.include_router(routes.router)

    response = TestClient(app).get(
        "/api/fetch-data",
        params={
            "lat": 10,
            "long": 20,
            "mission_start": START.isoformat(),
            "mission_end": END.isoformat(),
            "step": 120,
        },
    )

    assert response.status_code == 200
    assert response.json()["step_minutes"] == 120
    assert response.json()["scoring"]["metadata"]["sample_count"] == 12


def test_sunlight_duration_route_is_removed() -> None:
    app = FastAPI()
    app.include_router(routes.router)

    response = TestClient(app).get("/api/sunlight-duration")

    assert response.status_code == 404
