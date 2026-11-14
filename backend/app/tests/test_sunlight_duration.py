"""Unit and API tests for terrain-aware sunlight duration."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

import app.services.sunlight_duration as sunlight


START = datetime(2026, 11, 15, tzinfo=timezone.utc)


def horizon(unknown: bool = False) -> dict:
    """Accept a coverage flag; return a synthetic local terrain horizon."""
    return dict(
        profile=[
            dict(
                azimuth_deg=angle,
                horizon_elevation_deg=None if unknown and angle == 0 else 0.0,
            )
            for angle in (0, 90, 180, 270)
        ],
        metadata=dict(azimuth_step_deg=90.0),
        data_quality=(
            "insufficient_data"
            if unknown
            else "complete_within_radius"
        ),
    )


def positions(states: list[bool]) -> list[tuple[float, float]]:
    """Accept visibility states; return synthetic Sun angle pairs."""
    return [
        (0.0, 5.0 if state else -5.0)
        for state in states
    ]


def test_18_hours_of_sunlight(monkeypatch: pytest.MonkeyPatch) -> None:
    """Accept monkeypatch; verify 18 of 24 illuminated hours; return None."""
    monkeypatch.setattr(
        sunlight,
        "_horizons_positions",
        Mock(return_value=positions([True] * 18 + [False] * 6)),
    )

    result = sunlight.get_average_duration_of_sunlight(
        -85,
        30,
        START,
        START + timedelta(days=1),
        horizon_data=horizon(),
    )

    assert result["sunlight_fraction"] == pytest.approx(0.75)
    assert result["sunlight_percentage"] == pytest.approx(75)
    assert result["total_sunlight_hours"] == 18
    assert result["average_sunlight_hours_per_24h"] == 18
    assert result["longest_darkness_hours"] == 6

    assert result["sunlight_windows"] == [
        dict(
            start=START.isoformat(),
            end=(START + timedelta(hours=18)).isoformat(),
        )
    ]

    assert result["data_quality"] == "complete_within_radius"


def test_longest_darkness_is_contiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accept monkeypatch; verify longest continuous darkness; return None."""
    monkeypatch.setattr(
        sunlight,
        "_horizons_positions",
        Mock(
            return_value=positions([
                True, False, False, False, True, False
            ])
        ),
    )

    result = sunlight.get_average_duration_of_sunlight(
        -85,
        30,
        START,
        START + timedelta(hours=6),
        horizon_data=horizon(),
    )

    assert result["total_sunlight_hours"] == 2
    assert result["longest_darkness_hours"] == 3
    assert len(result["sunlight_windows"]) == 2


@pytest.mark.parametrize(
    "visible, expected",
    [
        (True, 1.0),
        (False, 0.0),
    ],
)
def test_constant_sunlight(
    monkeypatch: pytest.MonkeyPatch,
    visible: bool,
    expected: float,
) -> None:
    """Accept visibility and expected fraction; verify result; return None."""
    monkeypatch.setattr(
        sunlight,
        "_horizons_positions",
        Mock(return_value=positions([visible] * 4)),
    )

    result = sunlight.get_average_duration_of_sunlight(
        -85,
        30,
        START,
        START + timedelta(hours=4),
        horizon_data=horizon(),
    )

    assert result["sunlight_fraction"] == expected
    assert result["longest_darkness_hours"] == (
        0 if visible else 4
    )


def test_missing_terrain_yields_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accept monkeypatch; verify missing terrain handling; return None."""
    monkeypatch.setattr(
        sunlight,
        "_horizons_positions",
        Mock(return_value=positions([True, False])),
    )

    result = sunlight.get_average_duration_of_sunlight(
        -85,
        30,
        START,
        START + timedelta(hours=2),
        horizon_data=horizon(unknown=True),
    )

    assert result["sunlight_fraction"] is None
    assert result["longest_darkness_hours"] is None
    assert result["sunlight_windows"] is None
    assert result["unknown_samples"] == 2
    assert result["data_quality"] == "insufficient_data"


@pytest.mark.parametrize(
    "start,end,step",
    [
        (START, START, 60),
        (START, START + timedelta(minutes=70), 60),
        (
            START.replace(tzinfo=None),
            START + timedelta(hours=1),
            60,
        ),
        (START, START + timedelta(hours=1), 0),
        (START, START + timedelta(hours=1), True),
        (START, START + timedelta(days=400), 60),
    ],
)
def test_invalid_period(
    start: datetime,
    end: datetime,
    step: int,
) -> None:
    """Accept invalid time parameters; verify validation; return None."""
    with pytest.raises(ValueError):
        sunlight.get_average_duration_of_sunlight(
            -85,
            30,
            start,
            end,
            step_minutes=step,
            horizon_data=horizon(),
        )


@pytest.mark.parametrize(
    "lat,lon",
    [
        (91, 0),
        (-91, 0),
        (-85, 361),
        (-85, float("nan")),
    ],
)
def test_invalid_coordinates(
    lat: float,
    lon: float,
) -> None:
    """Accept invalid lunar coordinates; verify rejection; return None."""
    with pytest.raises(ValueError):
        sunlight.get_average_duration_of_sunlight(
            lat,
            lon,
            START,
            START + timedelta(hours=1),
            horizon_data=horizon(),
        )


class FakeResponse:
    """Represent the required methods of a mocked Horizons response."""

    def __init__(self, raw: str) -> None:
        """Accept Horizons text; initialize the response; return None."""
        self.raw = raw

    def raise_for_status(self) -> None:
        """Accept no arguments; represent HTTP success; return None."""
        return None

    def json(self) -> dict:
        """Accept no arguments; return a Horizons-compatible response."""
        return dict(result=self.raw)


def test_horizons_csv_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accept monkeypatch; verify Horizons CSV parsing; return None."""
    midpoints = [
        START + timedelta(minutes=30),
        START + timedelta(minutes=90),
    ]

    lines = [
        (
            f"{mid.timestamp() / 86400 + 2440587.5:.9f}, "
            f", , 90.0, {5.0 if i == 0 else -2.0},"
        )
        for i, mid in enumerate(midpoints)
    ]

    recorded = dict()

    def fake_get(
        url: str,
        *,
        params: dict,
        timeout: int,
    ) -> FakeResponse:
        """Accept HTTP parameters; record and return mock ephemerides."""
        recorded.update(params)

        return FakeResponse(
            "header\n$$SOE\n"
            + "\n".join(lines)
            + "\n$$EOE\n"
        )

    monkeypatch.setattr(
        sunlight.requests,
        "get",
        fake_get,
    )

    result = sunlight.get_average_duration_of_sunlight(
        -85,
        30,
        START,
        START + timedelta(hours=2),
        horizon_data=horizon(),
    )

    assert result["sunlight_fraction"] == 0.5
    assert result["longest_darkness_hours"] == 1

    assert recorded["COMMAND"] == "'10'"
    assert recorded["CAL_FORMAT"] == "'JD'"
    assert recorded["SITE_COORD"] == "'30,-85,0'"


def test_horizons_missing_rows_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accept monkeypatch; reject missing Horizons data; return None."""
    monkeypatch.setattr(
        sunlight.requests,
        "get",
        Mock(return_value=FakeResponse("$$SOE\n$$EOE")),
    )

    with pytest.raises(
        sunlight.SunlightDataUnavailable,
        match="returned 0 samples",
    ):
        sunlight.get_average_duration_of_sunlight(
            -85,
            30,
            START,
            START + timedelta(hours=2),
            horizon_data=horizon(),
        )


def test_horizon_loaded_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accept monkeypatch; verify horizon reuse; return None."""
    mocked_horizon = Mock(return_value=horizon())

    monkeypatch.setattr(
        sunlight,
        "get_terrain_horizon",
        mocked_horizon,
    )

    monkeypatch.setattr(
        sunlight,
        "_horizons_positions",
        Mock(return_value=positions([True, True])),
    )

    result = sunlight.get_average_duration_of_sunlight(
        -85,
        30,
        START,
        START + timedelta(hours=2),
    )

    assert result["sunlight_fraction"] == 1
    mocked_horizon.assert_called_once_with(-85, 30)


def test_sunlight_api_returns_typed_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accept monkeypatch; verify API response serialization; return None."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import app.routes as routes
    from app.routes import router

    reply = dict(
        latitude=-85.0,
        longitude=30.0,
        start_time=START.isoformat(),
        end_time=(START + timedelta(hours=2)).isoformat(),
        step_minutes=60,
        sample_count=2,
        unknown_samples=0,
        sunlight_fraction=0.5,
        sunlight_percentage=50.0,
        total_sunlight_hours=1.0,
        average_sunlight_hours_per_24h=12.0,
        longest_darkness_hours=1.0,
        sunlight_windows=[
            dict(
                start=START.isoformat(),
                end=(START + timedelta(hours=1)).isoformat(),
            )
        ],
        data_quality="complete_within_radius",
        horizon_data_quality="complete_within_radius",
    )

    monkeypatch.setattr(
        routes,
        "get_average_duration_of_sunlight",
        Mock(return_value=reply),
    )

    app = FastAPI()
    app.include_router(router)

    response = TestClient(app).get(
        "/api/sunlight-duration",
        params=dict(
            lat=-85,
            long=30,
            start=START.isoformat(),
            end=(START + timedelta(hours=2)).isoformat(),
            step_minutes=60,
        ),
    )

    assert response.status_code == 200, response.text
    assert response.json()["sunlight_fraction"] == 0.5
    assert response.json()["longest_darkness_hours"] == 1.0


def test_sunlight_api_rejects_naive_dates() -> None:
    """Accept no arguments; verify timezone validation; return None."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routes import router

    app = FastAPI()
    app.include_router(router)

    response = TestClient(app).get(
        "/api/sunlight-duration",
        params=dict(
            lat=-85,
            long=30,
            start="2026-11-15T00:00:00",
            end="2026-11-15T01:00:00",
            step_minutes=60,
        ),
    )

    assert response.status_code == 422


def test_reject_timezone_without_utc_offset() -> None:
    """Take no arguments; reject an invalid timezone; return None."""
    from datetime import tzinfo

    class NoOffsetTimezone(tzinfo):
        """Represent a timezone without a known UTC offset."""

        def utcoffset(self, dt: datetime) -> None:
            """Accept a datetime and return no UTC offset."""
            return None

        def dst(self, dt: datetime) -> None:
            """Accept a datetime and return no daylight saving offset."""
            return None

    invalid_start = START.replace(tzinfo=NoOffsetTimezone())

    with pytest.raises(ValueError, match="timezone"):
        sunlight.get_average_duration_of_sunlight(
            -85,
            30,
            invalid_start,
            START + timedelta(hours=2),
            horizon_data=horizon(),
        )


def test_horizons_explicit_error_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accept monkeypatch; reject an API error in HTTP 200; return None."""
    reply = Mock()
    reply.json.return_value = {
        "error": "Observer location is invalid"
    }

    monkeypatch.setattr(
        sunlight.requests,
        "get",
        Mock(return_value=reply),
    )

    with pytest.raises(
        sunlight.SunlightDataUnavailable,
        match="rejected",
    ):
        sunlight.get_average_duration_of_sunlight(
            -85,
            30,
            START,
            START + timedelta(hours=1),
            horizon_data=horizon(),
        )


def test_reject_wrong_horizons_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accept monkeypatch; reject mismatched ephemeris time; return None."""
    raw = (
        "header\n"
        "$$SOE\n"
        "2450000.5, , , 90.0, 5.0,\n"
        "$$EOE\n"
    )

    monkeypatch.setattr(
        sunlight.requests,
        "get",
        Mock(return_value=FakeResponse(raw)),
    )

    with pytest.raises(
        sunlight.SunlightDataUnavailable,
        match="Inconsistent",
    ):
        sunlight.get_average_duration_of_sunlight(
            -85,
            30,
            START,
            START + timedelta(hours=1),
            horizon_data=horizon(),
        )
