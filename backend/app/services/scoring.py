"""Independent lunar landing-site suitability scoring (model v1.0)."""

from dataclasses import dataclass
from math import exp, isclose, isfinite, sqrt
from typing import Any, Mapping, Sequence


MODEL_VERSION = "1.0"

METRIC_NAMES = (
    "sunlight_fraction",
    "longest_darkness_hours",
    "earth_visibility_fraction",
    "longest_earth_blackout_hours",
    "slope_p95_degrees",
)

NORMALIZED_NAMES = (
    "sunlight",
    "darkness_endurance",
    "earth_visibility",
    "communication_endurance",
    "slope_suitability",
)

COVERAGE_NAMES = (
    "solar_ephemeris",
    "earth_ephemeris",
    "dem",
    "slope_footprint",
)

DEFAULT_WEIGHTS = (0.25, 0.20, 0.15, 0.10, 0.30)


@dataclass(frozen=True)
class ScoringConfig:
    """Store validated mission-specific scoring settings."""

    tau_power_hours: float = 24.0
    tau_communication_hours: float = 120.0
    slope_reference_degrees: float = 10.0
    weights: tuple[float, ...] = DEFAULT_WEIGHTS
    max_slope_degrees: float | None = None
    max_darkness_hours: float | None = None
    max_earth_blackout_hours: float | None = None


def _number(value: object, name: str) -> float:
    """Accept a numeric value and field name; return a finite float."""
    if isinstance(value, (str, bytes, bool)):
        raise ValueError(f"{name} must be a finite number")

    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc

    if not isfinite(result):
        raise ValueError(f"{name} must be a finite number")

    return result


def _nonnegative(
    value: object,
    name: str,
    maximum: float | None = None,
) -> float:
    """Accept a value, field name and optional cap; return a valid float."""
    result = _number(value, name)

    if result < 0 or (maximum is not None and result > maximum):
        raise ValueError(
            f"{name} must be between 0 and "
            f"{maximum if maximum is not None else 'infinity'}"
        )

    return result


def _positive(value: object, name: str) -> float:
    """Accept a value and field name; return a strictly positive float."""
    result = _number(value, name)

    if result <= 0:
        raise ValueError(f"{name} must be positive")

    return result


def _validate_weights(value: object) -> tuple[float, ...]:
    """Accept a weight sequence; return five validated weights."""
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes)
    ):
        raise ValueError("weights must be a sequence of five numbers")

    if len(value) != len(METRIC_NAMES):
        raise ValueError("weights must contain exactly five elements")

    weights = tuple(_nonnegative(item, "weight") for item in value)

    if not isclose(
        sum(weights),
        1.0,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError("weights must sum to 1")

    return weights


def _optional_limit(
    config: Mapping[str, object],
    name: str,
    maximum: float | None = None,
) -> float | None:
    """Accept mission settings and a limit name; return float or None."""
    if name not in config or config[name] is None:
        return None

    return _nonnegative(config[name], name, maximum)


def _validated_config(
    mission_config: Mapping[str, object] | None,
) -> ScoringConfig:
    """Accept optional mission settings; return a validated config."""
    if mission_config is None:
        mission_config = dict()

    if not isinstance(mission_config, Mapping):
        raise ValueError("mission_config must be a mapping")

    return ScoringConfig(
        tau_power_hours=_positive(
            mission_config.get("tau_power_hours", 24.0),
            "tau_power_hours",
        ),
        tau_communication_hours=_positive(
            mission_config.get("tau_communication_hours", 120.0),
            "tau_communication_hours",
        ),
        slope_reference_degrees=_positive(
            mission_config.get("slope_reference_degrees", 10.0),
            "slope_reference_degrees",
        ),
        weights=_validate_weights(
            mission_config.get("weights", DEFAULT_WEIGHTS)
        ),
        max_slope_degrees=_optional_limit(
            mission_config,
            "max_slope_degrees",
            90.0,
        ),
        max_darkness_hours=_optional_limit(
            mission_config,
            "max_darkness_hours",
        ),
        max_earth_blackout_hours=_optional_limit(
            mission_config,
            "max_earth_blackout_hours",
        ),
    )


def _unavailable_sources(metrics: Mapping[str, object]) -> list[str]:
    """Accept site metrics; return names of unavailable data sources."""
    coverage = metrics.get("source_coverage")

    if coverage is None:
        return []

    if not isinstance(coverage, Mapping):
        raise ValueError("source_coverage must be a mapping")

    unavailable = []

    for name in COVERAGE_NAMES:
        status = coverage.get(name)

        if status is not None and not isinstance(status, bool):
            raise ValueError(
                f"source_coverage.{name} must be a boolean or None"
            )

        if status is not True:
            unavailable.append(name)

    return unavailable


def _metadata(metrics: Mapping[str, object]) -> dict[str, Any]:
    """Accept site metrics; return a copy of provenance metadata."""
    value = metrics.get("metadata")

    if value is None:
        return dict()

    if not isinstance(value, Mapping):
        raise ValueError("metadata must be a mapping")

    return dict(value)


def _empty_result(
    missing: list[str],
    unavailable: list[str],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Accept missing data details; return an unscored result."""
    return dict(
        score=None,
        feasible=None,
        failed_constraints=[],
        normalized_metrics=None,
        model_version=MODEL_VERSION,
        data_quality="insufficient_data",
        missing_metrics=missing,
        unavailable_sources=unavailable,
        metadata=metadata,
    )


def score_site(
    metrics: Mapping[str, object],
    mission_config: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Calculate a lunar landing-site suitability score.

    Args:
        metrics: Measured sunlight fraction, darkness duration,
            Earth visibility fraction, communication blackout
            duration and 95th-percentile terrain slope.
            Optional source_coverage and metadata are supported.
        mission_config: Optional scoring weights, reference scales
            and mission feasibility limits.

    Returns:
        Dictionary containing the 0-100 score, normalized metrics,
        feasibility status, failed constraints and data quality.
        Missing inputs produce an unscored result.
    """
    if not isinstance(metrics, Mapping):
        raise ValueError("metrics must be a mapping")

    config = _validated_config(mission_config)
    metadata = _metadata(metrics)
    unavailable = _unavailable_sources(metrics)

    missing = [
        name
        for name in METRIC_NAMES
        if name not in metrics or metrics[name] is None
    ]

    values = dict()

    for name in METRIC_NAMES:
        if name in missing:
            continue

        if name.endswith("_fraction"):
            maximum = 1.0
        elif name == "slope_p95_degrees":
            maximum = 90.0
        else:
            maximum = None

        values[name] = _nonnegative(metrics[name], name, maximum)

    if missing or unavailable:
        return _empty_result(missing, unavailable, metadata)

    sunlight = values["sunlight_fraction"]
    darkness = values["longest_darkness_hours"]
    earth_visibility = values["earth_visibility_fraction"]
    blackout = values["longest_earth_blackout_hours"]
    slope = values["slope_p95_degrees"]

    normalized = (
        sunlight,
        exp(-darkness / config.tau_power_hours),
        earth_visibility,
        exp(-blackout / config.tau_communication_hours),
        max(
            0.0,
            1.0 - (slope / config.slope_reference_degrees) ** 2,
        ),
    )

    distance_best = sqrt(
        sum(
            weight * (1.0 - value) ** 2
            for weight, value in zip(config.weights, normalized)
        )
    )

    distance_worst = sqrt(
        sum(
            weight * value ** 2
            for weight, value in zip(config.weights, normalized)
        )
    )

    score = (
        100.0
        * distance_worst
        / (distance_best + distance_worst)
    )

    failed_constraints = []

    limits = (
        ("max_slope_degrees", slope, config.max_slope_degrees),
        ("max_darkness_hours", darkness, config.max_darkness_hours),
        (
            "max_earth_blackout_hours",
            blackout,
            config.max_earth_blackout_hours,
        ),
    )

    has_constraints = False

    for name, observed, limit in limits:
        if limit is not None:
            has_constraints = True

            if observed > limit:
                failed_constraints.append(name)

    feasible = (
        not failed_constraints
        if has_constraints
        else None
    )

    data_quality = (
        "complete"
        if metrics.get("source_coverage") is not None
        else "metrics_complete_unverified"
    )

    return dict(
        score=score,
        feasible=feasible,
        failed_constraints=failed_constraints,
        normalized_metrics=dict(zip(NORMALIZED_NAMES, normalized)),
        model_version=MODEL_VERSION,
        data_quality=data_quality,
        missing_metrics=[],
        unavailable_sources=[],
        metadata=metadata,
    )


def get_score(
    metrics: Mapping[str, object],
    mission_config: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Accept site metrics and mission settings; return scoring results."""
    return score_site(metrics, mission_config)


def compare_sites(
    site_a: Mapping[str, object],
    site_b: Mapping[str, object],
    mission_config: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Compare two lunar landing sites using identical scoring criteria.

    Args:
        site_a: Measured metrics for the first landing site.
        site_b: Measured metrics for the second landing site.
        mission_config: Shared scoring settings and mission limits.

    Returns:
        Dictionary containing both results, score difference,
        Pareto dominance and the preferred site.
    """
    result_a = score_site(site_a, mission_config)
    result_b = score_site(site_b, mission_config)

    if result_a["score"] is None or result_b["score"] is None:
        return dict(
            site_a=result_a,
            site_b=result_b,
            delta_score=None,
            pareto_dominance=None,
            preferred_site=None,
        )

    a = tuple(result_a["normalized_metrics"].values())
    b = tuple(result_b["normalized_metrics"].values())

    if (
        all(x >= y for x, y in zip(a, b))
        and any(x > y for x, y in zip(a, b))
    ):
        dominance = "A"
    elif (
        all(y >= x for x, y in zip(a, b))
        and any(y > x for x, y in zip(a, b))
    ):
        dominance = "B"
    else:
        dominance = "neither"

    delta = result_a["score"] - result_b["score"]

    if (
        result_a["feasible"] is False
        and result_b["feasible"] is False
    ):
        preferred = None
    elif result_a["feasible"] is False:
        preferred = "B" if result_b["feasible"] is True else None
    elif result_b["feasible"] is False:
        preferred = "A" if result_a["feasible"] is True else None
    elif isclose(delta, 0.0, abs_tol=1e-12):
        preferred = "tie"
    else:
        preferred = "A" if delta > 0 else "B"

    return dict(
        site_a=result_a,
        site_b=result_b,
        delta_score=delta,
        pareto_dominance=dominance,
        preferred_site=preferred,
    )
