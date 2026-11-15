from typing import Any

from pydantic import BaseModel, Field


class ScoringResult(BaseModel):
    score: float | None = None
    feasible: bool | None = None
    failed_constraints: list[str] = Field(default_factory=list)
    normalized_metrics: dict[str, float] | None = None
    model_version: str
    data_quality: str
    missing_metrics: list[str] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FetchDataResponse(BaseModel):
    daytime_avg_sun_angle: float | None = None
    terrain_elevation_m: float | None = None
    visibility_windows: list | None = None
    ground_angle_deg: float | None = None
    lola_roughness_deg: float | None = Field(default=None, description="LOLA median absolute along-track slope in degrees over a 225 m baseline.",)
    score: float | None = Field(default=None, ge=0, le=100, description="Independent fixed-ideal TOPSIS landing-site score.",)
    scoring_metrics: dict[str, float | None] = Field(default_factory=dict)
    scoring: ScoringResult
