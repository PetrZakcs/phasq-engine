"""
Denní teplota a srážky — NASA POWER API (power.larc.nasa.gov), ne Open-Meteo.

PROČ ZMĚNA (2026-09-09): Open-Meteo je BEZPLATNÝ JEN PRO NEKOMERČNÍ POUŽITÍ
(https://open-meteo.com/en/terms) — pro komerční produkt vyžaduje placený
tarif. NASA POWER je zdarma pro JAKÉKOLIV použití včetně komerčního, bez
registrace, bez API klíče — a bez atribuce (NASA public domain policy).

Živě ověřeno: NASA POWER data mají ~9-10denní zpoždění (MERRA-2 reanalýza
ještě nedoběhla) — nevhodné pro "co se děje DNES", ale pro sezónní
agroklimatické součty (GDD, mrazová historie, srážkový deficit za měsíce)
to nevadí. Kořenová zóna (živý signál, latence vadí) je proto samostatný
modul — engine/datasources/nasa_power_rootzone.py (viz ADR-006), stejný
zdroj dat, jiná otázka (percentil vůči historii, ne jen součet).
"""

from dataclasses import dataclass
from datetime import datetime

import httpx

POWER_API_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"

PARAMETERS = "T2M_MAX,T2M_MIN,PRECTOTCORR"
FILL_VALUE = -999.0


@dataclass
class DailyWeather:
    dates: list[str]
    tmax: list[float]
    tmin: list[float]
    precipitation_mm: list[float]


def _to_power_date(iso_date: str) -> str:
    return iso_date.replace("-", "")


def _to_iso_date(power_date: str) -> str:
    return datetime.strptime(power_date, "%Y%m%d").strftime("%Y-%m-%d")


class NasaPowerWeatherSource:
    """Denní Tmax/Tmin/srážky pro daný bod a časové okno. Žádná autentizace, žádný API klíč."""

    async def get_daily_weather(self, lat: float, lon: float, start_date: str, end_date: str) -> DailyWeather:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                POWER_API_URL,
                params={
                    "parameters": PARAMETERS,
                    "community": "AG",  # agrometeorologická sada parametrů
                    "longitude": round(lon, 4),
                    "latitude": round(lat, 4),
                    "start": _to_power_date(start_date),
                    "end": _to_power_date(end_date),
                    "format": "JSON",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        params = data["properties"]["parameter"]
        tmax_raw = params["T2M_MAX"]
        tmin_raw = params["T2M_MIN"]
        precip_raw = params["PRECTOTCORR"]

        # Chybějící dny (fill_value -999.0, typicky posledních ~9-10 dní kvůli
        # zpoždění reanalýzy) se ZAHAZUJÍ, ne propouští jako falešná data —
        # jinak by GDD součet/mrazová detekce v agroclimate.py počítaly
        # s fyzikálně nesmyslnými -999°C dny.
        dates, tmax, tmin, precip = [], [], [], []
        for power_date in sorted(tmax_raw.keys()):
            if tmax_raw[power_date] == FILL_VALUE or tmin_raw[power_date] == FILL_VALUE or precip_raw[power_date] == FILL_VALUE:
                continue
            dates.append(_to_iso_date(power_date))
            tmax.append(tmax_raw[power_date])
            tmin.append(tmin_raw[power_date])
            precip.append(precip_raw[power_date])

        return DailyWeather(dates=dates, tmax=tmax, tmin=tmin, precipitation_mm=precip)
