"""
Vstupní modely API. Validace doplněna při bezpečnostním auditu 2026-10-14:
dřív šlo poslat libovolné datum/geometrii a neomezené lookback_years
(N let denních dat z NASA POWER na jeden request) a limit plochy AOI
platil jen pro Sentinel-1, ne pro truecolor/agroclimate.
"""

from datetime import date, timedelta

from pydantic import BaseModel, Field, field_validator, model_validator

from engine.datasources.sentinel1_cdse import MAX_AOI_HA
from utils.geometry import polygon_area_ha

# Delší okno nemá v žádném endpointu smysl a násobí počet volání CDSE.
MAX_DATE_RANGE_DAYS = 366
EARLIEST_DATE = date(2014, 10, 1)  # start Sentinel-1A operací
MAX_POLYGON_VERTICES = 5000


def _parse_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("datum musí být ve formátu YYYY-MM-DD")
    if len(value) != 10:
        raise ValueError("datum musí být ve formátu YYYY-MM-DD")
    if parsed < EARLIEST_DATE:
        raise ValueError(f"datum nesmí být před {EARLIEST_DATE.isoformat()}")
    if parsed > date.today() + timedelta(days=1):
        raise ValueError("datum nesmí být v budoucnosti")
    return parsed


def _validate_polygon(geometry: dict) -> dict:
    if not isinstance(geometry, dict) or geometry.get("type") != "Polygon":
        raise ValueError("geometrie musí být GeoJSON Polygon")
    coords = geometry.get("coordinates")
    if not isinstance(coords, list) or not coords or not isinstance(coords[0], list):
        raise ValueError("Polygon nemá platné souřadnice")
    ring = coords[0]
    if len(ring) < 4 or len(ring) > MAX_POLYGON_VERTICES:
        raise ValueError(f"Polygon musí mít 4 až {MAX_POLYGON_VERTICES} bodů")
    for point in ring:
        if (
            not isinstance(point, (list, tuple))
            or len(point) < 2
            or not all(isinstance(c, (int, float)) for c in point[:2])
            or not (-180 <= point[0] <= 180 and -90 <= point[1] <= 90)
        ):
            raise ValueError("Polygon obsahuje neplatný bod (očekává se [lon, lat] ve WGS84)")
    area = polygon_area_ha(geometry)
    if area <= 0:
        raise ValueError("Polygon má nulovou plochu")
    if area > MAX_AOI_HA:
        raise ValueError(f"AOI {area:.0f} ha přesahuje limit {MAX_AOI_HA:.0f} ha")
    return geometry


def _check_range(start: str, end: str) -> None:
    d_start, d_end = date.fromisoformat(start), date.fromisoformat(end)
    if d_end < d_start:
        raise ValueError("konec období je před začátkem")
    if (d_end - d_start).days > MAX_DATE_RANGE_DAYS:
        raise ValueError(f"období může mít nejvýš {MAX_DATE_RANGE_DAYS} dní")


class _GeometryRequest(BaseModel):
    geometry: dict = Field(..., description="GeoJSON Polygon AOI")

    @field_validator("geometry")
    @classmethod
    def _geometry(cls, v: dict) -> dict:
        return _validate_polygon(v)


class RadiometricAnalysisRequest(_GeometryRequest):
    date_start: str = Field(..., description="YYYY-MM-DD")
    date_end: str = Field(..., description="YYYY-MM-DD")
    orbit_direction: str = Field(default="BOTH", pattern="^(ASCENDING|DESCENDING|BOTH)$")

    @field_validator("date_start", "date_end")
    @classmethod
    def _date(cls, v: str) -> str:
        _parse_date(v)
        return v

    @model_validator(mode="after")
    def _range(self):
        _check_range(self.date_start, self.date_end)
        return self


class TrueColorImageRequest(_GeometryRequest):
    date_start: str = Field(..., description="YYYY-MM-DD")
    date_end: str = Field(..., description="YYYY-MM-DD")

    @field_validator("date_start", "date_end")
    @classmethod
    def _date(cls, v: str) -> str:
        _parse_date(v)
        return v

    @model_validator(mode="after")
    def _range(self):
        _check_range(self.date_start, self.date_end)
        return self


class AgroclimateRequest(_GeometryRequest):
    season_start: str = Field(..., description="YYYY-MM-DD, obvykle 1.1. aktuálního roku")
    as_of_date: str = Field(..., description="YYYY-MM-DD, dnešek/konec sledovaného období")
    gdd_base_temp: float = Field(default=5.0, ge=-5.0, le=20.0, description="Základní teplota pro GDD — plodino-specifická, 5.0 je default pro obiloviny střední Evropy")
    lookback_years: int = Field(default=5, ge=1, le=30, description="Kolik historických let pro srážkový normál")

    @field_validator("season_start", "as_of_date")
    @classmethod
    def _date(cls, v: str) -> str:
        _parse_date(v)
        return v

    @model_validator(mode="after")
    def _range(self):
        _check_range(self.season_start, self.as_of_date)
        return self
