from pydantic import BaseModel, Field


class RadiometricAnalysisRequest(BaseModel):
    geometry: dict = Field(..., description="GeoJSON Polygon AOI")
    date_start: str = Field(..., description="YYYY-MM-DD")
    date_end: str = Field(..., description="YYYY-MM-DD")
    orbit_direction: str = Field(default="BOTH", pattern="^(ASCENDING|DESCENDING|BOTH)$")
