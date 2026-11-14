
"""Unit tests for the lunar landing-site suitability scoring model."""

import math

import pytest

from app.services.scoring import compare_sites, get_score, score_site


def example_a() -> dict[str, float]:
    """Take no arguments; return metrics for example site A."""
    return dict(
        sunlight_fraction=0.80,
        longest_darkness_hours=8.0,
        earth_visibility_fraction=0.45,
        longest_earth_blackout_hours=120.0,
        slope_p95_degrees=4.0,
    )


def example_b() -> dict[str, float]:
    """Take no arguments; return metrics for example site B."""
    return dict(
        sunlight_fraction=0.72,
        longest_darkness_hours=3.0,
        earth_visibility_fraction=0.63,
        longest_earth_blackout_hours=80.0,
        slope_p95_degrees=6.0,
    )


def test_document_worked_example() -> None:
    """Take no arguments; verify example scores and comparison; return None."""
    comparison = compare_sites(example_a(), example_b())

    assert comparison["site_a"]["score"] == pytest.approx(67.60, abs=0.01)
    assert comparison["site_b"]["score"] == pytest.approx(68.40, abs=0.01)
    assert comparison["delta_score"] == pytest.approx(-0.80, abs=0.01)
    assert comparison["pareto_dominance"] == "neither"
    assert comparison["preferred_site"] == "B"


def test_perfect_site_is_100() -> None:
    """Take no arguments; verify the ideal site gets 100; return None."""
    metrics = dict(
        sunlight_fraction=1.0,
        longest_darkness_hours=0,
        earth_visibility_fraction=1.0,
        longest_earth_blackout_hours=0,
        slope_p95_degrees=0,
    )

    assert score_site(metrics)["score"] == pytest.approx(100)


def test_worst_site_is_0() -> None:
    """Take no arguments; verify the worst site gets zero; return None."""
    metrics = dict(
        sunlight_fraction=0.0,
        longest_darkness_hours=1_000_000,
        earth_visibility_fraction=0.0,
        longest_earth_blackout_hours=1_000_000,
        slope_p95_degrees=90.0,
    )

    assert score_site(metrics)["score"] == pytest.approx(0)


def test_independence_from_other_sites() -> None:
    """Take no arguments; verify independent scoring; return None."""
    original = score_site(example_a())
    comparison = compare_sites(example_a(), example_b())

    assert original["score"] == comparison["site_a"]["score"]


def test_outages_cannot_improve_score() -> None:
    """Take no arguments; verify outage penalties; return None."""
    initial = example_a()
    darkness = dict(initial, longest_darkness_hours=48)
    blackout = dict(initial, longest_earth_blackout_hours=300)

    assert score_site(darkness)["score"] < score_site(initial)["score"]
    assert score_site(blackout)["score"] < score_site(initial)["score"]


def test_slope_constraint_overrides_numeric_score() -> None:
    """Take no arguments; verify feasibility overrides score; return None."""
    high_score = dict(
        sunlight_fraction=1,
        longest_darkness_hours=0,
        earth_visibility_fraction=1,
        longest_earth_blackout_hours=0,
        slope_p95_degrees=8,
    )

    lower_score = example_a()
    config = dict(max_slope_degrees=5)

    comparison = compare_sites(high_score, lower_score, config)

    assert comparison["site_a"]["score"] > comparison["site_b"]["score"]
    assert comparison["site_a"]["feasible"] is False
    assert comparison["site_a"]["failed_constraints"] == [
        "max_slope_degrees"
    ]
    assert comparison["preferred_site"] == "B"


def test_missing_constraints_are_unknown() -> None:
    """Take no arguments; verify unknown feasibility; return None."""
    assert score_site(example_a())["feasible"] is None


def test_all_limits_are_checked() -> None:
    """Take no arguments; verify all mission limits; return None."""
    config = dict(
        max_slope_degrees=3,
        max_darkness_hours=7,
        max_earth_blackout_hours=119,
    )

    result = score_site(example_a(), config)

    assert result["feasible"] is False
    assert result["failed_constraints"] == [
        "max_slope_degrees",
        "max_darkness_hours",
        "max_earth_blackout_hours",
    ]


def test_both_infeasible_sites_are_not_preferred() -> None:
    """Take no arguments; reject both infeasible sites; return None."""
    result = compare_sites(
        example_a(),
        example_b(),
        dict(max_slope_degrees=2),
    )

    assert result["preferred_site"] is None


def test_missing_metric_returns_insufficient_data() -> None:
    """Take no arguments; verify missing metric handling; return None."""
    metrics = example_a()
    del metrics["earth_visibility_fraction"]

    result = score_site(metrics)

    assert result["score"] is None
    assert result["feasible"] is None
    assert result["data_quality"] == "insufficient_data"
    assert result["missing_metrics"] == ["earth_visibility_fraction"]


def test_coverage_is_checked() -> None:
    """Take no arguments; verify missing source coverage; return None."""
    metrics = dict(
        example_a(),
        source_coverage=dict(
            solar_ephemeris=True,
            earth_ephemeris=False,
            dem=True,
            slope_footprint=True,
        ),
    )

    result = score_site(metrics)

    assert result["score"] is None
    assert result["data_quality"] == "insufficient_data"
    assert result["unavailable_sources"] == ["earth_ephemeris"]


def test_partial_coverage_is_unavailable() -> None:
    """Take no arguments; verify incomplete coverage; return None."""
    metrics = dict(
        example_a(),
        source_coverage=dict(dem=True),
    )

    result = score_site(metrics)

    assert result["score"] is None
    assert result["unavailable_sources"] == [
        "solar_ephemeris",
        "earth_ephemeris",
        "slope_footprint",
    ]


def test_null_coverage_is_not_claimed_complete() -> None:
    """Take no arguments; verify unverified source data; return None."""
    result = score_site(
        dict(example_a(), source_coverage=None)
    )

    assert result["data_quality"] == "metrics_complete_unverified"


def test_confirmed_coverage_and_provenance() -> None:
    """Take no arguments; verify complete data provenance; return None."""
    provenance = dict(
        dem_resolution_m=80,
        time_step_minutes=120,
        landing_footprint_m=50,
    )

    metrics = dict(
        example_a(),
        source_coverage=dict(
            solar_ephemeris=True,
            earth_ephemeris=True,
            dem=True,
            slope_footprint=True,
        ),
        metadata=provenance,
    )

    result = score_site(metrics)

    assert result["data_quality"] == "complete"
    assert result["metadata"] == provenance


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("sunlight_fraction", -0.1),
        ("sunlight_fraction", 1.1),
        ("earth_visibility_fraction", math.nan),
        ("longest_darkness_hours", -1),
        ("longest_earth_blackout_hours", math.inf),
        ("slope_p95_degrees", 91),
        ("slope_p95_degrees", "2.5"),
        ("sunlight_fraction", True),
    ],
)
def test_invalid_metrics_raise_value_error(
    field: str,
    invalid: object,
) -> None:
    """Take an invalid metric and value; verify rejection; return None."""
    metrics = dict(example_a())
    metrics[field] = invalid

    with pytest.raises(ValueError):
        score_site(metrics)


@pytest.mark.parametrize(
    "config",
    [
        dict(tau_power_hours=0),
        dict(tau_communication_hours=-1),
        dict(slope_reference_degrees=math.inf),
        dict(weights=[0.1, 0.2]),
        dict(weights=[0.2, 0.2, 0.2, 0.2, 0.1]),
        dict(weights=[0.2, 0.2, 0.2, 0.2, -0.1]),
        dict(max_slope_degrees=-1),
        dict(max_darkness_hours=-1),
    ],
)
def test_invalid_configuration_raises_value_error(
    config: dict[str, object],
) -> None:
    """Take invalid mission settings; verify rejection; return None."""
    with pytest.raises(ValueError):
        score_site(example_a(), config)


def test_custom_weights_change_only_selected_metric_importance() -> None:
    """Take no arguments; verify custom scoring weights; return None."""
    metrics = example_a()
    config = dict(weights=[1, 0, 0, 0, 0])

    assert score_site(metrics, config)["score"] == pytest.approx(80.0)


def test_pareto_dominance() -> None:
    """Take no arguments; verify Pareto dominance; return None."""
    ideal = dict(
        sunlight_fraction=1,
        longest_darkness_hours=0,
        earth_visibility_fraction=1,
        longest_earth_blackout_hours=0,
        slope_p95_degrees=0,
    )

    result = compare_sites(ideal, example_a())

    assert result["pareto_dominance"] == "A"


def test_compare_cannot_rank_missing_site() -> None:
    """Take no arguments; verify missing site handling; return None."""
    empty = dict(example_a(), slope_p95_degrees=None)

    result = compare_sites(empty, example_b())

    assert result["delta_score"] is None
    assert result["pareto_dominance"] is None
    assert result["preferred_site"] is None


def test_get_score_alias() -> None:
    """Take no arguments; verify the score wrapper; return None."""
    assert get_score(example_a()) == score_site(example_a())
