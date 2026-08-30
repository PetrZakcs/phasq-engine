"""
Lokální historická dry/wet reference pro RadiometricAnalyzer — TU Wien
change detection metoda (Bauer-Marschallinger et al. 2019, Wagner et al. 1999)
POŘÁDNĚ, ne přes jednu univerzální dvojici konstant pro celou střední Evropu.

Proč tohle existuje (živě ověřeno 2026-08-30, viz docs/ADR-002-local-baseline.md):
Globální SIGMA_DRY_REF_DB=-22/SIGMA_WET_REF_DB=-8 z master_plan.md daly na
reálném LPIS poli (35.6 ha orná půda, Havlíčkobrodsko) relative_moisture_pct
84 % a "no drought" v době, kdy Intersucho.cz hlásí pro stejný region
"výjimečné až extrémní sucho". Roční historie téhož pole má rozpětí jen
-15.71 až -7.98 dB — nikdy se neblíží ke globální -22 dB "suché" referenci.

Metoda: pro dané AOI stáhni N měsíců/let historie Ïƒâ° (per-scéna mean_db,
ne surové pixely — přes CDSE Statistical API, stejně jako běžná analýza),
a jako lokální referenci vezmi nízký/vysoký percentil z TÉTO distribuce,
ne mean. Percentil na dB hodnotách je v pořádku (order statistic, ne
průměr — nenarazí na chybu #3 z master_plan.md popsanou v radiometric.py).
"""

from dataclasses import dataclass

import numpy as np

from engine.datasources.base import DataSource

MIN_HISTORICAL_SCENES = 20  # pod touto hranicí je percentil nedůvěryhodný, radši spadnout na global fallback


@dataclass
class LocalReference:
    dry_db: float
    wet_db: float
    scenes_used: int
    lookback_days: int


class InsufficientHistory(Exception):
    pass


class HistoricalBaselineCalculator:
    """
    Fáze 1 stav: počítá se on-demand při každém requestu — DRAHÉ (roční
    historie = ~190 CDSE Statistical API voláních zabalených v jednom
    requestu, ~4s). Cachování per-AOI (Supabase, refresh třeba měsíčně,
    ne při každé analýze) je Fáze 3 TODO, ne vyřešeno tady.
    """

    def __init__(self, source: DataSource, lookback_days: int = 365, dry_percentile: float = 5.0, wet_percentile: float = 95.0):
        self.source = source
        self.lookback_days = lookback_days
        self.dry_percentile = dry_percentile
        self.wet_percentile = wet_percentile

    async def compute(self, geometry: dict, as_of_date: str) -> LocalReference:
        from datetime import datetime, timedelta

        end = datetime.strptime(as_of_date, "%Y-%m-%d")
        start = end - timedelta(days=self.lookback_days)

        scenes = await self.source.get_scenes(
            geometry=geometry,
            date_start=start.strftime("%Y-%m-%d"),
            date_end=end.strftime("%Y-%m-%d"),
            polarizations=["VV"],
            orbit_direction="BOTH",
        )

        valid = [s for s in scenes if s.roi_stats.valid_pixel_ratio >= 0.5]
        if len(valid) < MIN_HISTORICAL_SCENES:
            raise InsufficientHistory(
                f"Jen {len(valid)} platných historických scén za {self.lookback_days} dní "
                f"(potřeba aspoň {MIN_HISTORICAL_SCENES}). Fallback na globální referenci."
            )

        db_values = np.array([s.roi_stats.mean_db for s in valid])
        dry_db = float(np.percentile(db_values, self.dry_percentile))
        wet_db = float(np.percentile(db_values, self.wet_percentile))

        return LocalReference(
            dry_db=dry_db,
            wet_db=wet_db,
            scenes_used=len(valid),
            lookback_days=self.lookback_days,
        )
