from pydantic import BaseModel, Field
from datetime import datetime


class FetchDataResponse(BaseModel):
    daytime_avg_sun_angle: float | None = None
    terrain_elevation_m: float | None = None
    visibility_windows: list | None = None
    ground_angle_deg: float | None = None
    lola_roughness_deg: float | None = Field(
        default=None,
        description="LOLA median absolute along-track slope in degrees over a 225 m baseline.",
    )


class SunlightWindow(BaseModel):
    start: datetime
    end: datetime


class SunlightDurationResponse(BaseModel):
    latitude: float
    longitude: float
    start_time: datetime
    end_time: datetime
    step_minutes: int
    sample_count: int
    unknown_samples: int

    sunlight_fraction: float | None
    sunlight_percentage: float | None
    total_sunlight_hours: float | None
    average_sunlight_hours_per_24h: float | None
    longest_darkness_hours: float | None

    sunlight_windows: list[SunlightWindow] | None

    data_quality: str
    horizon_data_quality: str | None
