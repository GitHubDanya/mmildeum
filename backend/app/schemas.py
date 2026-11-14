from pydantic import BaseModel, Field


class TerrainRoughnessMetadata(BaseModel):
    dataset: str = Field(description="Filename of the source elevation raster.")
    resolution_deg: tuple[float, float] = Field(description="Native longitude and latitude pixel spacing in degrees.")
    window_size_m: int = Field(description="Side length in meters of the square centered on the site in the DEM's coordinate frame.")
    valid_sample_count: int = Field(description="Number of native cell centers with valid elevations inside the square.")
    sample_count: int = Field(description="Total number of native cell centers inside the square.")


class FetchDataResponse(BaseModel):
    terrain_type: str | None
    terrain_class_id: int | None = Field(description="Published NASA LOLA south-pole roughness class ID.")
    daytime_avg_sun_angle: float | None = None
    terrain_elevation_m: float | None = None
    visibility_windows: list | None = None
    ground_angle_deg: float | None = None
    terrain_roughness_m: float | None = Field(
        default=None,
        description="Area-weighted RMS elevation in meters about a best-fit plane, estimated from the global DEM.",
    )
    terrain_roughness_metadata: TerrainRoughnessMetadata | None = None
