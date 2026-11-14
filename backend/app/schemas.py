from pydantic import BaseModel

class FetchDataResponse(BaseModel):
    terrain_type: str | None
    terrain_class_id: int | None
    daytime_avg_sun_angle: float | None
