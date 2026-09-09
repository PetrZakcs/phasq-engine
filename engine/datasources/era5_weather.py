"""
Denní teplota a srážky z ERA5-Land (přes Open-Meteo Historical Weather API,
stejný zdroj jako engine/datasources/era5_land.py, bez nutné registrace).

Slouží jako vstup pro engine/physics/agroclimate.py (growing degree days,
mrazová rizika, srážkový deficit) — fáze B "dokončovacího" plánu pro
zemědělský vertikál, viz docs/ADR-004-agroclimate.md.
"""

from dataclasses import dataclass

import httpx

ARCHIVE_API_URL = "https://archive-api.open-meteo.com/v1/archive"


@dataclass
class DailyWeather:
    dates: list[str]
    tmax: list[float]
    tmin: list[float]
    precipitation_mm: list[float]


class Era5WeatherSource:
    """Denní Tmax/Tmin/srážky pro daný bod a časové okno. Žádná autentizace."""

    async def get_daily_weather(self, lat: float, lon: float, start_date: str, end_date: str) -> DailyWeather:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                ARCHIVE_API_URL,
                params={
                    "latitude": round(lat, 4),
                    "longitude": round(lon, 4),
                    "start_date": start_date,
                    "end_date": end_date,
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
                    "timezone": "auto",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        daily = data["daily"]
        return DailyWeather(
            dates=daily["time"],
            tmax=daily["temperature_2m_max"],
            tmin=daily["temperature_2m_min"],
            precipitation_mm=daily["precipitation_sum"],
        )
