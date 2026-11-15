"""Tests for terrain-aware Earth visibility metrics."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app.services import earth_visibility as earth


START = datetime(2026, 11, 15, tzinfo=timezone.utc)


def horizon(*, unknown: bool = False) -> dict:
    return {
        "profile": [
            {
                "azimuth_deg": angle,
                "horizon_elevation_deg": (
                    None if unknown and angle == 0 else 0.0
                ),
            }
            for angle in (0, 90, 180, 270)
        ],
        "metadata": {"azimuth_step_deg": 90.0},
        "data_quality": (
            "insufficient_data" if unknown else "complete_within_radius"
        ),
    }


def positions(states: list[bool]) -> list[tuple[float, float]]:
    return [(0.0, 5.0 if state else -5.0) for state in states]


def test_visibility_fraction_and_longest_blackout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        earth,
        "_horizons_positions",
        Mock(
            return_value=positions(
                [True, False, False, True, False, False]
            )
        ),
    )

    result = earth.get_earth_visibility_window(
        -85,
        30,
        START,
        START + timedelta(hours=6),
        horizon_data=horizon(),
    )

    assert result["earth_visibility_fraction"] == pytest.approx(1 / 3)
    assert result["longest_earth_blackout_hours"] == 2
    assert result["windows"] == [
        {
            "start": START.isoformat(),
            "end": (START + timedelta(hours=1)).isoformat(),
        },
        {
            "start": (START + timedelta(hours=3)).isoformat(),
            "end": (START + timedelta(hours=4)).isoformat(),
        },
    ]


def test_unknown_horizon_returns_insufficient_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        earth,
        "_horizons_positions",
        Mock(return_value=positions([True, False])),
    )

    result = earth.get_earth_visibility_window(
        -85,
        30,
        START,
        START + timedelta(hours=2),
        horizon_data=horizon(unknown=True),
    )

    assert result["earth_visibility_fraction"] is None
    assert result["longest_earth_blackout_hours"] is None
    assert result["windows"] is None
    assert result["unknown_samples"] == 2
    assert result["data_quality"] == "insufficient_data"


class FakeResponse:
    def __init__(self, raw: str) -> None:
        self.raw = raw

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"result": self.raw}


def test_horizons_request_uses_earth_and_requested_epochs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    midpoint = START + timedelta(minutes=30)
    julian_day = midpoint.timestamp() / 86400.0 + 2440587.5
    recorded = {}

    def fake_get(url: str, *, params: dict, timeout: int) -> FakeResponse:
        recorded.update(params)
        return FakeResponse(
            f"header\n$$SOE\n{julian_day:.9f}, , , 90.0, 5.0,\n$$EOE\n"
        )

    monkeypatch.setattr(earth.requests, "get", fake_get)

    result = earth.get_earth_visibility_window(
        -85,
        30,
        START,
        START + timedelta(hours=1),
        horizon_data=horizon(),
    )

    assert result["earth_visibility_fraction"] == 1.0
    assert recorded["COMMAND"] == "'399'"
    assert recorded["START_TIME"] == "'2026-11-15 00:30:00'"
    assert recorded["STEP_SIZE"] == "'60 m'"
