
# Lunar Landing Site Navigator — Backend

## Landing-Site Scoring (Issue #20)

The scoring implementation is located in:

`app/services/scoring.py`

It uses the Fixed-Ideal TOPSIS model (v1.0) to evaluate
potential lunar landing sites.

The model ranks sites based on solar illumination,
Earth visibility, communication outages and terrain slope.

The scoring function does not retrieve NASA data directly.
All required metrics must be calculated by other services.

## Required Metrics

| Metric | Description |
| --- | --- |
| `sunlight_fraction` | Fraction of time with sunlight (0–1) |
| `longest_darkness_hours` | Longest continuous darkness period |
| `earth_visibility_fraction` | Fraction of time with Earth visibility (0–1) |
| `longest_earth_blackout_hours` | Longest communication blackout |
| `slope_p95_degrees` | 95th-percentile terrain slope |

## Example Usage

```python
from app.services.scoring import score_site

metrics = dict(
    sunlight_fraction=0.80,
    longest_darkness_hours=8.0,
    earth_visibility_fraction=0.45,
    longest_earth_blackout_hours=120.0,
    slope_p95_degrees=4.0,
)

config = dict(
    max_slope_degrees=5.0,
)

result = score_site(metrics, config)

print(result["score"])
print(result["feasible"])
```

Expected score: approximately 67.60.

## Scoring Configuration

The model supports the following settings:

- `tau_power_hours`: default 24
- `tau_communication_hours`: default 120
- `slope_reference_degrees`: default 10
- `weights`: default [0.25, 0.20, 0.15, 0.10, 0.30]
- `max_slope_degrees`: optional
- `max_darkness_hours`: optional
- `max_earth_blackout_hours`: optional

These are prototype parameters, not NASA-approved
landing safety thresholds.

## Data Validation

The scoring function validates its inputs.

Missing required measurements produce:

- `score = None`
- `feasible = None`
- `data_quality = "insufficient_data"`

Invalid numerical values raise `ValueError`.

Optional `source_coverage` flags can indicate whether
the required ephemeris and terrain data are available.

Optional `metadata` can contain DEM resolution,
time step, landing footprint and data sources.

## Comparing Landing Sites

Use `compare_sites()` to compare two candidates.

```python
from app.services.scoring import compare_sites

comparison = compare_sites(site_a, site_b, config)

print(comparison["delta_score"])
print(comparison["pareto_dominance"])
print(comparison["preferred_site"])
```

Both sites must use the same mission interval,
sampling step, footprint and scoring settings.

The score is a mission suitability index,
not a guarantee of safe landing.

## API Integration

`GET /api/fetch-data` derives all five required measurements over a shared
ephemeris period and returns the independent score in `score`. The complete
result, including normalized metrics, data quality, source coverage and
provenance, is returned in `scoring`; the measured inputs are returned in
`scoring_metrics`.

The terrain metric is the 95th-percentile slope from 25 samples over a
circular footprint. Its radius defaults to 250 m and can be changed with the
`footprint_radius_m` query parameter (up to 5 km). If an ephemeris or any
required footprint sample is unavailable, the endpoint still returns site
data but reports an unscored `insufficient_data` result instead of assigning a
misleading score.

## Running Tests

From the `backend` directory:

```bash
uv run --with pytest python -m pytest -q app/tests/test_scoring.py
```
