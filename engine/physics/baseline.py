"""
Lokální historická dry/wet reference pro RadiometricAnalyzer — TU Wien
change detection metoda (Bauer-Marschallinger et al. 2019, Wagner et al. 1999)
POŘÁDNĚ, ne přes jednu univerzální dvojici konstant pro celou střední Evropu.

Proč tohle existuje (živě ověřeno 2026-08-30, viz docs/ADR-002-local-baseline.md):
Globální SIGMA_DRY_REF_DB=-22/SIGMA_WET_REF_DB=-8 z master_plan.md daly na
reálném LPIS poli (35.6 ha orná půda, Havlíčkobrodsko) relative_moisture_pct
84 % a "no drought" v době, kdy Intersucho.cz hlásí pro stejný region
"výjimečné až extrémní sucho".

DRUHÁ oprava (živě ověřeno stejný den, viz ADR-002 "Sezónní kontaminace"):
první verze tohohle modulu brala PROSTÝ rolling N-day lookback (365 dní).
To selhalo na cross-region srovnání dvou polí — jedno z nich mělo v části
roku (jiná sezóna, jiná plodina/fáze osevního postupu) Ïƒâ° kolem -4 až -6 dB
(typické pro hustou vegetaci jako kukuřici v plné biomase — objemový
rozptyl, ne vlhkost půdy), zatímco ve stejné sezóně jako aktuální analýza
bylo -10 až -12 dB. Prostý 365denní percentil tuhle úplně jinou fyziku
namíchal do "wet" reference a zkreslil ji.

Oprava: SEZÓNNÍ okno napříč VÍCE LETY (stejné kalendářní období, minulé
roky) — ne "posledních N dní". Referenci nikdy netvoří aktuální rok
(jinak by probíhající sucho samo zředilo vlastní referenci).

Metoda: pro dané AOI a datum stáhni Ïƒâ° scény ze stejného ±W-denního okna
kolem stejného dne v roce, za posledních K let (bez aktuálního roku), a
jako referenci vezmi nízký/vysoký percentil z TÉTO distribuce, ne mean.
Percentil na dB hodnotách je v pořádku (order statistic, ne průměr —
nenarazí na chybu #3 z master_plan.md popsanou v radiometric.py).
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

from engine.datasources.base import DataSource

MIN_HISTORICAL_SCENES = 20  # pod touto hranicí je percentil nedůvěryhodný, radši spadnout na global fallback


@dataclass
class LocalReference:
    dry_db: float
    wet_db: float
    scenes_used: int
    years_used: list = field(default_factory=list)
    seasonal_window_days: int = 0


class InsufficientHistory(Exception):
    pass


class HistoricalBaselineCalculator:
    """
    Fáze 1 stav: počítá se on-demand při každém requestu — DRAHÉ (K let ×
    ~6 týdnů okno = víc CDSE Statistical API volání v jednom requestu,
    řádově sekundy až nízké desítky sekund). Cachování per-AOI (Supabase,
    refresh třeba měsíčně, ne při každé analýze) je Fáze 3 TODO.
    """

    def __init__(
        self,
        source: DataSource,
        lookback_years: int = 5,
        seasonal_window_days: int = 21,
        dry_percentile: float = 5.0,
        wet_percentile: float = 95.0,
    ):
        self.source = source
        self.lookback_years = lookback_years
        self.seasonal_window_days = seasonal_window_days
        self.dry_percentile = dry_percentile
        self.wet_percentile = wet_percentile

    async def compute(self, geometry: dict, as_of_date: str) -> LocalReference:
        as_of = datetime.strptime(as_of_date, "%Y-%m-%d")

        all_values: list[float] = []
        years_with_data: list[int] = []

        for years_back in range(1, self.lookback_years + 1):
            # Stejný den v roce, N let zpátky — NIKDY aktuální rok.
            try:
                center = as_of.replace(year=as_of.year - years_back)
            except ValueError:
                # 29. únor v roce, co ho nemá
                center = as_of.replace(year=as_of.year - years_back, day=28)

            window_start = center - timedelta(days=self.seasonal_window_days)
            window_end = center + timedelta(days=self.seasonal_window_days)

            scenes = await self.source.get_scenes(
                geometry=geometry,
                date_start=window_start.strftime("%Y-%m-%d"),
                date_end=window_end.strftime("%Y-%m-%d"),
                polarizations=["VV"],
                orbit_direction="BOTH",
            )
            valid = [s for s in scenes if s.roi_stats.valid_pixel_ratio >= 0.5]
            if valid:
                years_with_data.append(center.year)
                all_values.extend(s.roi_stats.mean_db for s in valid)

        if len(all_values) < MIN_HISTORICAL_SCENES:
            raise InsufficientHistory(
                f"Jen {len(all_values)} platných historických scén napříč "
                f"{self.lookback_years} lety (±{self.seasonal_window_days}d okno kolem "
                f"{as_of.strftime('%m-%d')}), potřeba aspoň {MIN_HISTORICAL_SCENES}. "
                f"Fallback na globální referenci."
            )

        db_values = np.array(all_values)
        dry_db = float(np.percentile(db_values, self.dry_percentile))
        wet_db = float(np.percentile(db_values, self.wet_percentile))

        return LocalReference(
            dry_db=dry_db,
            wet_db=wet_db,
            scenes_used=len(all_values),
            years_used=years_with_data,
            seasonal_window_days=self.seasonal_window_days,
        )
