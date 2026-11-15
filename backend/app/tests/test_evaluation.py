"""Tests for shared scoring-metric evaluation helpers."""

import pytest
from app.services.evaluation import availability_metrics


def test_availability_metrics_returns_fraction_and_longest_outage() -> None:
    result = availability_metrics(
        [True, False, False, True, False, False, False, True],
        step_hours=2.0,
    )
    assert result == pytest.approx((0.375, 6.0))


def test_availability_metrics_does_not_join_period_boundaries() -> None:
    result = availability_metrics([False, True, True, False], step_hours=1.0)
    assert result == pytest.approx((0.5, 1.0))


def test_availability_metrics_rejects_empty_series() -> None:
    assert availability_metrics([], step_hours=1.0) is None
