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
roku (jiná sezóna, jiná plodina/fáze osevního postupu) σ⁰ kolem -4 až -6 dB
(typické pro hustou vegetaci jako kukuřici v plné biomase — objemový
rozptyl, ne vlhkost půdy), zatímco ve stejné sezóně jako aktuální analýza
bylo -10 až -12 dB. Prostý 365denní percentil tuhle úplně jinou fyziku
namíchal do "wet" reference a zkreslil ji.

Oprava: SEZÓNNÍ okno napříč VÍCE LETY (stejné kalendářní období, minulé
roky) — ne "posledních N dní". Referenci nikdy netvoří aktuální rok
(jinak by probíhající sucho samo zředilo vlastní referenci).

TŘETÍ oprava (viz ADR-002 "Co je skutečně potřeba k uzavření"): ani
sezónní okno nerozliší mokrou půdu od husté vegetace v plné biomase —
obojí zvedá backscatter, jen z různé fyziky. Volitelný `ndvi_source`
(Sentinel2NDVISource) vyřadí scény s hustým porostem z reference i z
aktuálního okna — bez něj se chová jako dřív, s ním se do LocalReference
zapisuje kolik scén to vyřadilo, transparentně, ne potichu.

Metoda: pro dané AOI a datum stáhni σ⁰ scény ze stejného ±W-denního okna
kolem stejného dne v roce, za posledních K let (bez aktuálního roku), a
jako referenci vezmi nízký/vysoký percentil z TÉTO distribuce, ne mean.
Percentil na dB hodnotách je v pořádku (order statistic, ne průměr —
nenarazí na chybu #3 z master_plan.md popsanou v radiometric.py).
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

from engine.datasources.base import DataSource
from engine.datasources.sentinel2_cdse import (
    DENSE_VEGETATION_NDVI_THRESHOLD,
    Sentinel2NDVISource,
    nearest_ndvi,
)

MIN_SCENES_PER_YEAR = 8  # pod touto hranicí je percentil JEDNOHO roku nedůvěryhodný, ten rok se do mediánu nepočítá
MIN_YEARS_FOR_MEDIAN = 3  # medián z míň než 3 hodnot není o moc lepší než jedna hodnota
NDVI_MATCH_MAX_DAYS_GAP = 5  # S1/S2 revizit se neshoduje den na den


@dataclass
class LocalReference:
    dry_db: float
    wet_db: float
    scenes_used: int
    years_used: list = field(default_factory=list)
    seasonal_window_days: int = 0
    ndvi_gated: bool = False
    dense_vegetation_scenes_excluded: int = 0
    dense_vegetation_ndvi_threshold_used: float | None = None


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
        ndvi_source: Sentinel2NDVISource | None = None,
        lookback_years: int = 5,
        seasonal_window_days: int = 21,
        dry_percentile: float = 5.0,
        wet_percentile: float = 95.0,
        dense_vegetation_ndvi_threshold: float = DENSE_VEGETATION_NDVI_THRESHOLD,
    ):
        self.source = source
        self.ndvi_source = ndvi_source
        self.lookback_years = lookback_years
        self.seasonal_window_days = seasonal_window_days
        self.dry_percentile = dry_percentile
        self.wet_percentile = wet_percentile
        # Parametrizováno 2026-10-13 (ADR-011) - výchozí hodnota =
        # DENSE_VEGETATION_NDVI_THRESHOLD, chování beze změny, dokud ho
        # volající explicitně nepřepíše.
        self.dense_vegetation_ndvi_threshold = dense_vegetation_ndvi_threshold

    async def compute(self, geometry: dict, as_of_date: str) -> LocalReference:
        """
        ČTVRTÁ oprava (viz ADR-002 "NDVI hradlo padlo pod vlastní kontrolou"):
        NDVI hradlo je zapojené, ale samo o sobě nestačilo — anomální rok
        (drsnost povrchu / mokrá půda po žních, ne vegetace) leží PŘESNĚ v
        sezónním okně, takže NDVI ho nevyřadí a sezónní okno ho taky
        nemůže odfiltrovat (není mimo sezónu). Řešíme to jinak: percentil
        se počítá PER ROK, referencí je MEDIÁN z ročních percentilů, ne
        percentil z jednoho poolu všech scén napříč lety. Jeden anomální
        rok pak přispěje jedním bodem do mediánu pěti hodnot, ne desítkami
        scén do poolu stovek.
        """
        as_of = datetime.strptime(as_of_date, "%Y-%m-%d")

        per_year_dry: list[float] = []
        per_year_wet: list[float] = []
        years_with_data: list[int] = []
        dense_excluded = 0
        total_scenes = 0

        for years_back in range(1, self.lookback_years + 1):
            # Stejný den v roce, N let zpátky — NIKDY aktuální rok.
            try:
                center = as_of.replace(year=as_of.year - years_back)
            except ValueError:
                # 29. únor v roce, co ho nemá
                center = as_of.replace(year=as_of.year - years_back, day=28)

            window_start = center - timedelta(days=self.seasonal_window_days)
            window_end = center + timedelta(days=self.seasonal_window_days)
            window_start_str = window_start.strftime("%Y-%m-%d")
            window_end_str = window_end.strftime("%Y-%m-%d")

            scenes = await self.source.get_scenes(
                geometry=geometry,
                date_start=window_start_str,
                date_end=window_end_str,
                polarizations=["VV"],
                orbit_direction="BOTH",
            )
            valid = [s for s in scenes if s.roi_stats.valid_pixel_ratio >= 0.5]

            if valid and self.ndvi_source is not None:
                ndvi_series = await self.ndvi_source.get_ndvi_series(geometry, window_start_str, window_end_str)
                kept = []
                for s in valid:
                    nd = nearest_ndvi(ndvi_series, s.acquisition_date, max_days_gap=NDVI_MATCH_MAX_DAYS_GAP)
                    if nd is not None and nd.is_dense_vegetation(self.dense_vegetation_ndvi_threshold):
                        dense_excluded += 1
                        continue
                    kept.append(s)
                valid = kept

            # Percentil z jediného roku je nedůvěryhodný pod tímhle počtem
            # scén — takový rok se do mediánu nezapočítá, ne že by se
            # vynutil s malým vzorkem.
            if len(valid) >= MIN_SCENES_PER_YEAR:
                year_db_values = [s.roi_stats.mean_db for s in valid]
                per_year_dry.append(float(np.percentile(year_db_values, self.dry_percentile)))
                per_year_wet.append(float(np.percentile(year_db_values, self.wet_percentile)))
                years_with_data.append(center.year)
                total_scenes += len(valid)

        if len(per_year_dry) < MIN_YEARS_FOR_MEDIAN:
            raise InsufficientHistory(
                f"Jen {len(per_year_dry)} let s dostatečným počtem scén (≥{MIN_SCENES_PER_YEAR}) "
                f"napříč {self.lookback_years} lety (±{self.seasonal_window_days}d okno kolem "
                f"{as_of.strftime('%m-%d')}), potřeba aspoň {MIN_YEARS_FOR_MEDIAN} let "
                f"({dense_excluded} scén navíc vyřazeno kvůli husté vegetaci). "
                f"Fallback na globální referenci."
            )

        dry_db = float(np.median(per_year_dry))
        wet_db = float(np.median(per_year_wet))

        return LocalReference(
            dry_db=dry_db,
            wet_db=wet_db,
            scenes_used=total_scenes,
            years_used=years_with_data,
            seasonal_window_days=self.seasonal_window_days,
            ndvi_gated=self.ndvi_source is not None,
            dense_vegetation_scenes_excluded=dense_excluded,
            dense_vegetation_ndvi_threshold_used=(
                self.dense_vegetation_ndvi_threshold if self.ndvi_source is not None else None
            ),
        )
