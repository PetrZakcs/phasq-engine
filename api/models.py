from pydantic import BaseModel, Field


class RadiometricAnalysisRequest(BaseModel):
    geometry: dict = Field(..., description="GeoJSON Polygon AOI")
    date_start: str = Field(..., description="YYYY-MM-DD")
    date_end: str = Field(..., description="YYYY-MM-DD")
    orbit_direction: str = Field(default="BOTH", pattern="^(ASCENDING|DESCENDING|BOTH)$")


class AgroclimateRequest(BaseModel):
    geometry: dict = Field(..., description="GeoJSON Polygon AOI")
    season_start: str = Field(..., description="YYYY-MM-DD, obvykle 1.1. aktuálního roku")
    as_of_date: str = Field(..., description="YYYY-MM-DD, dnešek/konec sledovaného období")
    gdd_base_temp: float = Field(default=5.0, description="Základní teplota pro GDD — plodino-specifická, 5.0 je default pro obiloviny střední Evropy")
    lookback_years: int = Field(default=5, description="Kolik historických let pro srážkový normál")
