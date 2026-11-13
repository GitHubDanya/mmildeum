from pydantic import BaseModel

class FetchDataResponse(BaseModel):
    terrain_type: str | None
    terrain_class_id: int | None
    terrain_elevation_m: float | None = None 