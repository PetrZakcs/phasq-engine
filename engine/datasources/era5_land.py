"""
Kořenová zóna přes ERA5-Land reanalýzu (Copernicus Climate Change Service,
C3S) — nezávislý druhý zdroj, ne přepočet Sentinel-1 signálu.

PROČ TOHLE EXISTUJE (živě ověřeno 2026-09-09, viz docs/ADR-003-era5-fusion.md):
`root_zone_swi_pct` (engine/physics/root_zone.py) je časová extrapolace
POVRCHOVÉHO SAR signálu — matematický trik nad daty, co fyzicky nikdy
neviděla hlouběji než ~5 cm. Na reálném poli dal 45,2 % ("mild"), zatímco
Intersucho.cz hlásí pro stejné pole "výjimečné až extrémní sucho".

ERA5-Land je jiná fyzika: land-surface model (Copernicus/ECMWF), co
asimiluje srážky/teplotu/radiaci a SKUTEČNĚ POČÍTÁ vodní bilanci ve
4 hloubkových vrstvách (0-7, 7-28, 28-100, 100-255 cm) — ne extrapoluje
povrch, modeluje celý profil. Vrstva 28-100 cm odpovídá přibližně
Intersucho vrstvě "50-100 cm".

Živě ověřeno na stejném poli (Havlíčkobrodsko, 49.41N 15.54E), 9. 9. 2026:
dnešní hodnota vrstvy 28-100 cm (0.185 m³/m³) je POD MINIMEM celé
5leté historie pro totéž sezónní okno (215 historických hodnot,
min=0.245) — nejsušší den v datové řadě, ne jen "nízký percentil".
To se řádově líp shoduje s Intersucho "extrémní sucho" než SAR signál.

ZDROJ: Open-Meteo Historical Weather API (archive-api.open-meteo.com),
veřejné REST rozhraní BEZ nutné registrace, přímo obsluhuje ERA5-Land
data od Copernicus C3S. Žádný API klíč, žádný CDS účet.

DŮLEŽITÉ ROZHODNUTÍ: tenhle signál se do RadiometricAnalyzer výstupu
zapojuje jako SAMOSTATNÉ, jasně odlišené pole (`era5_root_zone_*`), NE
smíchaný do `relative_moisture_pct` ani do `root_zone_swi_pct`. Dva
nezávislé zdroje s různou fyzikou a různým rozlišením (10 m SAR vs. ~9 km
reanalýza) se nemají tiše průměrovat do jednoho čísla — to by jen
schovalo nesouhlas mezi nimi, místo aby ho ukázalo.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx
import numpy as np

ARCHIVE_API_URL = "https://archive-api.open-meteo.com/v1/archive"

# 28-100 cm nejblíž odpovídá Intersucho hloubkovým stanicím "50-100 cm".
DEFAULT_DEPTH_LAYER = "soil_moisture_28_to_100cm_mean"

MIN_HISTORICAL_SAMPLES = 30  # pod touto hranicí je percentil nedůvěryhodný


@dataclass
class Era5RootZoneReading:
    current_vwc: float  # m³/m³, volumetrická vlhkost
    percentile_rank: float  # 0-100, pozice dnešní hodnoty v historickém okně
    historical_min: float
    historical_max: float
    historical_samples: int
    depth_layer: str
    below_historical_range: bool  # dnešní hodnota je pod minimem historie - silnější signál než "nízký percentil"


class Era5InsufficientHistory(Exception):
    pass


class Era5LandSource:
    """
    Nezávislý root-zone signál z ERA5-Land reanalýzy, přes Open-Meteo.
    Žádná autentizace. Jedno HTTP volání pokryje celou historii i dnešek
    (archive API bere jeden souvislý date range, filtrování na sezónní
    okno napříč lety se dělá lokálně po stažení).
    """

    def __init__(self, depth_layer: str = DEFAULT_DEPTH_LAYER, lookback_years: int = 5, seasonal_window_days: int = 21):
        self.depth_layer = depth_layer
        self.lookback_years = lookback_years
        self.seasonal_window_days = seasonal_window_days

    async def get_root_zone_reading(self, lat: float, lon: float, as_of_date: str) -> Era5RootZoneReading:
        as_of = datetime.strptime(as_of_date, "%Y-%m-%d")
        start = as_of.replace(year=as_of.year - self.lookback_years, month=1, day=1)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                ARCHIVE_API_URL,
                params={
                    "latitude": round(lat, 4),
                    "longitude": round(lon, 4),
                    "start_date": start.strftime("%Y-%m-%d"),
                    "end_date": as_of.strftime("%Y-%m-%d"),
                    "daily": self.depth_layer,
                    "timezone": "auto",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        return self._compute_reading(data, as_of)

    def _compute_reading(self, raw: dict, as_of: datetime) -> Era5RootZoneReading:
        dates = raw["daily"]["time"]
        values = raw["daily"][self.depth_layer]

        by_date = {d: v for d, v in zip(dates, values) if v is not None}
        as_of_str = as_of.strftime("%Y-%m-%d")

        if as_of_str not in by_date:
            raise Era5InsufficientHistory(f"ERA5-Land nemá data pro {as_of_str} (reanalýza má obvykle několikadenní zpoždění).")

        today_vwc = by_date[as_of_str]

        historical: list[float] = []
        for d, v in by_date.items():
            dt = datetime.strptime(d, "%Y-%m-%d")
            if dt.year == as_of.year:
                continue  # nikdy aktuální rok do vlastní reference - stejné pravidlo jako u SAR baseline
            try:
                dt_this_year = dt.replace(year=as_of.year)
            except ValueError:
                dt_this_year = dt.replace(year=as_of.year, day=28)
            if abs((dt_this_year - as_of).days) <= self.seasonal_window_days:
                historical.append(v)

        if len(historical) < MIN_HISTORICAL_SAMPLES:
            raise Era5InsufficientHistory(
                f"Jen {len(historical)} historických vzorků v ±{self.seasonal_window_days}d okně "
                f"(potřeba aspoň {MIN_HISTORICAL_SAMPLES})."
            )

        historical.sort()
        hist_min, hist_max = historical[0], historical[-1]
        rank = sum(1 for v in historical if v <= today_vwc) / len(historical) * 100

        return Era5RootZoneReading(
            current_vwc=today_vwc,
            percentile_rank=round(rank, 1),
            historical_min=round(hist_min, 4),
            historical_max=round(hist_max, 4),
            historical_samples=len(historical),
            depth_layer=self.depth_layer,
            below_historical_range=today_vwc < hist_min,
        )


def geometry_centroid(geometry: dict) -> tuple[float, float]:
    """Vrátí (lat, lon) centroidu GeoJSON Polygonu. ERA5-Land má ~9 km rozlišení,
    přesná pozice v rámci pole nehraje roli - centroid stačí."""
    coords = geometry["coordinates"][0]
    lon = sum(c[0] for c in coords) / len(coords)
    lat = sum(c[1] for c in coords) / len(coords)
    return lat, lon
