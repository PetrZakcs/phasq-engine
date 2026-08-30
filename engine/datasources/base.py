"""
DataSource abstrakce — viz phasq_cto_master_plan.md sekce 1.2 a docs/ADR-001-data-source.md.

Physics Engine nesmí nic vědět o tom, odkud data pocházejí (CDSE dnes, dron nebo
komerční SAR poskytovatel zítra). Dostane SAR_Scene objekty, vrátí dict s výsledky.

Odchylka od master planu (zdokumentovaná v ADR-001): SAR_Scene nese primárně
`roi_stats` (server-side zredukované, filtrované statistiky), ne povinnou plnou
pixelovou matici. Plné pole je opt-in přes get_scene_arrays() pro moduly, které
ho skutečně potřebují (PolSAR, InSAR — fáze 2).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass
class ROIStats:
    """
    Server-side zredukované statistiky Ïƒâ° (dB) přes AOI pro jednu scénu.
    Počítáno na straně zdroje (CDSE Statistical API), včetně speckle filtru
    aplikovaného PŘED redukcí — viz chyba #4 v master planu.
    """
    mean_db: float
    p10_db: float
    p90_db: float
    stddev_db: float
    valid_pixel_ratio: float  # 0-1, podíl platných (ne-oblačných/no-data) pixelů v AOI


@dataclass
class SAR_Scene:
    """Standardizovaný vstupní formát pro Physics Engine — nezávislý na zdroji."""

    acquisition_date: str            # "YYYY-MM-DD"
    polarization: str                # "VV", "VH", "HH", "HV"
    orbit_direction: str             # "ASCENDING", "DESCENDING"
    instrument_mode: str             # "IW", "EW", "SM"
    roi_stats: ROIStats              # primární pole pro Fázi 1 (radiometric, snow)
    spatial_resolution_m: float
    crs: str
    bbox: tuple                      # (min_lon, min_lat, max_lon, max_lat)
    source_id: str                   # ID scény u poskytovatele
    metadata: dict = field(default_factory=dict)
    backscatter_db: Optional[np.ndarray] = None  # plná matice — jen fáze 2, opt-in


class DataSource(ABC):
    """Abstraktní rozhraní pro všechny zdroje SAR dat."""

    @abstractmethod
    async def get_scenes(
        self,
        geometry: dict,           # GeoJSON Polygon
        date_start: str,
        date_end: str,
        polarizations: list[str],
        **kwargs,
    ) -> list[SAR_Scene]:
        """Vrátí seznam scén s roi_stats pro zadané AOI a časové okno."""
        raise NotImplementedError

    @abstractmethod
    async def get_scene_count(self, geometry: dict, date_start: str, date_end: str) -> int:
        """Vrátí počet dostupných scén — pro validaci před spuštěním analýzy."""
        raise NotImplementedError

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Identifikátor zdroje — např. 'sentinel1_cdse', 'drone_sar'."""
        raise NotImplementedError

    @property
    @abstractmethod
    def typical_resolution_m(self) -> float:
        raise NotImplementedError


class MaxAOIExceeded(Exception):
    """AOI je příliš velké pro daný zdroj/operaci (viz limity v konkrétní implementaci)."""
