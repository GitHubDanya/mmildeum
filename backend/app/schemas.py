from pydantic import BaseModel, Field


class FetchDataResponse(BaseModel):
    daytime_avg_sun_angle: float | None = None
    terrain_elevation_m: float | None = None
    visibility_windows: list | None = None
    ground_angle_deg: float | None = None
    lola_roughness_deg: float | None = Field(
        default=None,
        description="LOLA median absolute along-track slope in degrees over a 225 m baseline.",
    )
