"""
Kořenová zóna přes NASA POWER (GWETROOT) — nezávislý druhý zdroj vůči
Sentinel-1 SAR, ne přepočet povrchového signálu.

PROČ TOHLE (2026-09-09, viz docs/ADR-006-nasa-power-rootzone.md): ADR-003
původně použil ERA5-Land přes Open-Meteo. Živě ověřeno, že Open-Meteo
zdarma tarif je JEN PRO NEKOMERČNÍ POUŽITÍ (open-meteo.com/en/pricing —
"Free tarif je zakázán pro komerční účely"). NASA POWER je zdarma pro
JAKÉKOLIV použití, bez registrace, bez API klíče, bez atribuce (NASA
public domain policy) — žádné budoucí "musíme přepnout, až budeme mít
peníze", je to vyřešené natrvalo.

CENA ZA TO: NASA POWER (MERRA-2 reanalýza) má reálné zpoždění ~9-10 dní
— živě ověřeno 2026-09-09. Proto se tohle NEPREZENTUJE jako "dnešní
stav", ale jako zpožděné nezávislé potvrzení — `effective_date` a
`lag_days` v odpovědi říkají přesně, jak staré číslo skutečně je,
nikdy se to nemaskuje jako aktuální.

GWETROOT je frakce nasycení (0-1), ne m³/m³ jako ERA5-Land — jiná
škála, ale stejný princip vyhodnocení: percentil vůči víceleté historii
stejného sezónního období, ne absolutní číslo bez kontextu.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx

POWER_API_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
FILL_VALUE = -999.0

MIN_HISTORICAL_SAMPLES = 30


@dataclass
class RootZoneReading:
    current_wetness: float  # frakce 0-1 (GWETROOT)
    effective_date: str  # datum, ke kterému hodnota SKUTEČNĚ patří (ne as_of_date)
    lag_days: int  # kolik dní stará je data proti as_of_date
    percentile_rank: float
    historical_min: float
    historical_max: float
    historical_samples: int
    below_historical_range: bool


class RootZoneInsufficientHistory(Exception):
    pass


class NasaPowerRootZoneSource:
    """Nezávislý root-zone signál z NASA POWER/MERRA-2. Žádná autentizace, žádný API klíč."""

    def __init__(self, lookback_years: int = 5, seasonal_window_days: int = 21):
        self.lookback_years = lookback_years
        self.seasonal_window_days = seasonal_window_days

    async def get_root_zone_reading(self, lat: float, lon: float, as_of_date: str) -> RootZoneReading:
        as_of = datetime.strptime(as_of_date, "%Y-%m-%d")
        start = as_of.replace(year=as_of.year - self.lookback_years, month=1, day=1)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                POWER_API_URL,
                params={
                    "parameters": "GWETROOT",
                    "community": "AG",
                    "longitude": round(lon, 4),
                    "latitude": round(lat, 4),
                    "start": start.strftime("%Y%m%d"),
                    "end": as_of.strftime("%Y%m%d"),
                    "format": "JSON",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        return self._compute_reading(data, as_of)

    def _compute_reading(self, raw: dict, as_of: datetime) -> RootZoneReading:
        raw_values = raw["properties"]["parameter"]["GWETROOT"]
        by_date = {
            datetime.strptime(d, "%Y%m%d"): v
            for d, v in raw_values.items()
            if v != FILL_VALUE
        }
        if not by_date:
            raise RootZoneInsufficientHistory("Žádná platná NASA POWER data v období.")

        # Nejnovější DOSTUPNÉ datum <= as_of_date — NASA POWER má ~9-10denní
        # zpoždění, exaktní as_of_date skoro nikdy nebude v datech. Poctivě
        # se to reportuje jako effective_date/lag_days, ne skrývá.
        available_dates = sorted(d for d in by_date if d <= as_of)
        if not available_dates:
            raise RootZoneInsufficientHistory(f"Žádná NASA POWER data do {as_of.strftime('%Y-%m-%d')}.")

        effective_date = available_dates[-1]
        current_wetness = by_date[effective_date]
        lag_days = (as_of - effective_date).days

        historical: list[float] = []
        for d, v in by_date.items():
            if d.year == effective_date.year:
                continue  # nikdy stejný rok jako referenční hodnota - stejné pravidlo jako SAR baseline
            try:
                d_this_year = d.replace(year=effective_date.year)
            except ValueError:
                d_this_year = d.replace(year=effective_date.year, day=28)
            if abs((d_this_year - effective_date).days) <= self.seasonal_window_days:
                historical.append(v)

        if len(historical) < MIN_HISTORICAL_SAMPLES:
            raise RootZoneInsufficientHistory(
                f"Jen {len(historical)} historických vzorků v ±{self.seasonal_window_days}d okně "
                f"(potřeba aspoň {MIN_HISTORICAL_SAMPLES})."
            )

        historical.sort()
        hist_min, hist_max = historical[0], historical[-1]
        rank = sum(1 for v in historical if v <= current_wetness) / len(historical) * 100

        return RootZoneReading(
            current_wetness=round(current_wetness, 4),
            effective_date=effective_date.strftime("%Y-%m-%d"),
            lag_days=lag_days,
            percentile_rank=round(rank, 1),
            historical_min=round(hist_min, 4),
            historical_max=round(hist_max, 4),
            historical_samples=len(historical),
            below_historical_range=current_wetness < hist_min,
        )


def geometry_centroid(geometry: dict) -> tuple[float, float]:
    """(lat, lon) centroidu GeoJSON Polygonu — NASA POWER má ~50km rozlišení, přesná pozice v poli nehraje roli."""
    coords = geometry["coordinates"][0]
    lon = sum(c[0] for c in coords) / len(coords)
    lat = sum(c[1] for c in coords) / len(coords)
    return lat, lon
