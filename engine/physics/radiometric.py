"""
Radiometrická analýza (vlhkost půdy) ze Sentinel-1 σ⁰ backscatteru.
Metoda: Change Detection (Bauer-Marschallinger et al. 2019), doi:10.3390/rs11050526

PLATÍ PRO: zemědělská půda střední Evropy, VV polarizace, IW mode,
holá/řídce vegetovaná půda. Hloubka měření ~0-5 cm (C-band).
NEPLATÍ PRO: hustá vegetace, zmrzlá půda, urbánní oblasti.

Oprava proti master_plan.md pseudokódu (chyba #2/#3 v tomtéž dokumentu, sekce 8):
ten samotný dokument varuje "průměr v dB škále je matematicky špatně", ale
referenční pseudokód (`mean_vv = np.mean(vv_values)` nad dB hodnotami) přesně
tuto chybu dělá. Tady se agreguje přes lineární škálu, viz db_to_linear/
linear_to_db a mean_backscatter_db níže.

Druhá oprava, nalezená živou validací 2026-08-30 proti Intersucho.cz
(viz docs/ADR-002-local-baseline.md, engine/physics/baseline.py):
globální SIGMA_DRY_REF_DB/SIGMA_WET_REF_DB jsou fallback pro AOI bez
dostatečné historie, NE primární zdroj pravdy. Primární je per-AOI lokální
baseline z HistoricalBaselineCalculator — bez ní analyzer na reálném poli
ukázal "no drought" během nezávisle potvrzeného extrémního sucha.

Třetí oprava, 2026-09-09 (viz docs/ADR-003-era5-fusion.md, ADR-006):
i s lokální baseline a SWI kořenovou zónou analyzer na reálném poli
dál podhodnocuje sucho proti Intersucho ("mild" místo "extrémní") —
protože Sentinel-1 fyzicky nevidí hlouběji než ~5 cm, žádná kalibrace
nad TÍMHLE vstupem to nezmění. Řešení není lepší matematika nad
stejnými daty, je to DRUHÝ, nezávislý zdroj, co skutečně modeluje
hlubší vrstvu. Zapojen jako samostatné pole (`power_root_zone_*`), NE
smíchaný do relative_moisture_pct/root_zone_swi_pct — dva různé zdroje
s různou fyzikou se nemají tiše průměrovat do jednoho čísla.

ADR-006 (2026-09-09): zdroj přepnut z ERA5-Land/Open-Meteo na NASA
POWER — živě ověřeno, že Open-Meteo zdarma tarif je JEN pro nekomerční
použití. NASA POWER je zdarma pro cokoliv, natrvalo, žádné budoucí
"přepneme, až budeme mít peníze". Cena: ~9-10denní zpoždění, proto
`power_root_zone_effective_date`/`power_root_zone_lag_days` v odpovědi
— nikdy se to nemaskuje jako aktuální stav.
"""

import numpy as np

from engine.datasources.base import SAR_Scene
from engine.datasources.nasa_power_rootzone import RootZoneReading
from engine.physics.baseline import LocalReference
from engine.physics.root_zone import compute_swi
from utils.decibel import db_to_linear, linear_to_db  # noqa: F401 - re-exportováno, testy importují odsud

SIGMA_DRY_REF_DB = -22.0
SIGMA_WET_REF_DB = -8.0

MIN_VALID_PIXEL_RATIO = 0.5  # scéna s méně platnými pixely v AOI se zahazuje

# Hranice severity v % relativní vlhkosti — NEZÁVISLÉ na tom, jestli je
# reference lokální nebo globální (dřív byly hranice v absolutních dB,
# což dávalo smysl jen pro jednu konkrétní referenční škálu — nekonzistentní
# už jen tím, že modul zároveň tvrdil, že referenci definuje).
SEVERITY_THRESHOLDS_PCT = [
    (70.0, "none"),
    (55.0, "mild"),
    (35.0, "moderate"),
    (20.0, "severe"),
]  # pod 20 % = "extreme"


def mean_backscatter_db(db_values: list[float]) -> float:
    """Průměr přes VÍCE scén musí jít přes lineární škálu, ne přímo v dB."""
    if not db_values:
        return 0.0
    linear_values = [db_to_linear(v) for v in db_values]
    return linear_to_db(float(np.mean(linear_values)))


class RadiometricAnalyzer:

    def analyze(
        self,
        scenes: list[SAR_Scene],
        roi_geometry: dict,
        local_reference: LocalReference | None = None,
        swi_t_days: float = 20.0,
        power_reading: RootZoneReading | None = None,
    ) -> dict:
        valid_scenes = [s for s in scenes if s.roi_stats.valid_pixel_ratio >= MIN_VALID_PIXEL_RATIO]
        dropped = len(scenes) - len(valid_scenes)

        if not valid_scenes:
            return self._error_response(
                "no_scenes",
                f"Žádné scény s dostatečným pokrytím AOI (zahozeno {dropped} kvůli nízkému valid_pixel_ratio)."
                if dropped
                else "Žádné scény k analýze.",
            )

        valid_scenes = sorted(valid_scenes, key=lambda s: s.acquisition_date)

        timeseries = [
            {
                "date": s.acquisition_date,
                "vv_db": round(s.roi_stats.mean_db, 2),
                "p10_db": round(s.roi_stats.p10_db, 2),
                "p90_db": round(s.roi_stats.p90_db, 2),
                "orbit": s.orbit_direction,
                "source": s.source_id,
            }
            for s in valid_scenes
        ]

        db_values = [s.roi_stats.mean_db for s in valid_scenes]
        mean_vv = mean_backscatter_db(db_values)
        trend_db = self._linear_trend_db(db_values)

        if local_reference is not None:
            dry_db, wet_db = local_reference.dry_db, local_reference.wet_db
            reference_source = "local_baseline"
        else:
            dry_db, wet_db = SIGMA_DRY_REF_DB, SIGMA_WET_REF_DB
            reference_source = "global_fallback"

        relative_moisture = self._sigma_to_moisture_pct(mean_vv, dry_db, wet_db)

        # ADR-008: global_fallback nesmí vydávat verdikt. Nalezeno externí
        # review + živě potvrzeno v ADR-007 (vlajkové pole spadlo na
        # global_fallback a dostalo "89 %, none" - DÁL od Intersucho reality
        # než předchozí vadný běh). Stejné globální konstanty už jednou v
        # ADR-002 daly "84 %, no drought" během nezávisle potvrzeného
        # extrémního sucha - text schovaný v alert_message to nestačí
        # ochránit, drought_severity/drought_risk se dřív četly samostatně.
        # relative_moisture_pct zůstává (syrové orientační číslo), ale
        # verdikt (severity/risk) je jen tam, kde je reference lokální.
        if reference_source == "local_baseline":
            drought_risk, severity = self._assess_drought(relative_moisture)
        else:
            drought_risk, severity = None, "unknown"

        # Kořenová zóna (viz engine/physics/root_zone.py): SWI exponenciální
        # filtr nad per-scéna povrchovou vlhkostí, T z literatury (default
        # 20 dní), NE lokálně kalibrované. Indikativní, ne validované číslo
        # — proto zvlášť pole, ne smíchané do relative_moisture_pct.
        per_scene_moisture = [self._sigma_to_moisture_pct(v, dry_db, wet_db) for v in db_values]
        scene_dates = [s.acquisition_date for s in valid_scenes]
        swi_series = compute_swi(scene_dates, per_scene_moisture, t_days=swi_t_days)
        for entry, swi_val in zip(timeseries, swi_series):
            entry["root_zone_swi_pct"] = round(swi_val, 1)
        root_zone_swi_pct = round(swi_series[-1], 1) if swi_series else None

        return {
            "success": True,
            "analysis_type": "radiometric",
            "data_source": valid_scenes[0].source_id.split("/")[0],
            "scenes_count": len(valid_scenes),
            "scenes_dropped_low_coverage": dropped,
            "mean_backscatter_vv_db": round(mean_vv, 2),
            "relative_moisture_pct": round(relative_moisture, 1),
            "root_zone_swi_pct": root_zone_swi_pct,
            "root_zone_swi_t_days": swi_t_days,
            "trend_db": round(trend_db, 2),
            "drought_risk": drought_risk,
            "drought_severity": severity,
            "alert_message": self._alert_message(severity, trend_db, reference_source),
            "timeseries": timeseries,
            "methodology": "change_detection",
            "reference_source": reference_source,
            "reference_dry_db": round(dry_db, 2),
            "reference_wet_db": round(wet_db, 2),
            "reference_scenes_used": local_reference.scenes_used if local_reference else None,
            "reference_years_used": local_reference.years_used if local_reference else None,
            "reference_seasonal_window_days": local_reference.seasonal_window_days if local_reference else None,
            "citation": "Bauer-Marschallinger et al. (2019), doi:10.3390/rs11050526",
            "spatial_resolution_m": valid_scenes[0].spatial_resolution_m,
            # Nezávislý druhý zdroj (NASA POWER, viz engine/datasources/
            # nasa_power_rootzone.py a ADR-006). Záměrně samostatná pole,
            # ne smíchaná s relative_moisture_pct/root_zone_swi_pct — jiná
            # fyzika (land-surface model, ne SAR), jiné rozlišení (~50 km
            # vs. 10 m), a ~9-10denní zpoždění (effective_date/lag_days
            # říká přesně jak staré, nikdy se to netváří jako aktuální).
            "power_root_zone_wetness": power_reading.current_wetness if power_reading else None,
            "power_root_zone_percentile_rank": power_reading.percentile_rank if power_reading else None,
            "power_root_zone_below_historical_range": power_reading.below_historical_range if power_reading else None,
            "power_root_zone_effective_date": power_reading.effective_date if power_reading else None,
            "power_root_zone_lag_days": power_reading.lag_days if power_reading else None,
            "power_root_zone_historical_samples": power_reading.historical_samples if power_reading else None,
            "measurement_caveat": (
                "Sentinel-1 C-band VV měří přímo jen vlhkost svrchní vrstvy půdy "
                "(~0-5 cm). root_zone_swi_pct je časová extrapolace (Wagner et al. "
                "1999 SWI filtr, T=" + f"{swi_t_days:.0f}" + " dní) nad TÍMTO povrchovým "
                "signálem — ne nezávislé měření hloubky." + (
                    " power_root_zone_percentile_rank je NEZÁVISLÝ druhý zdroj "
                    "(NASA POWER/MERRA-2 land-surface model), modeluje skutečnou "
                    "vodní bilanci v hloubce, ne extrapolaci povrchu — ALE je to "
                    f"{power_reading.lag_days if power_reading else '?'} dní staré "
                    f"(ke dni {power_reading.effective_date if power_reading else '?'}), "
                    "ne dnešní stav. Zpožděné, ne nedůvěryhodné."
                    if power_reading else
                    " Nezávislý hloubkový zdroj (NASA POWER) nebyl pro tuhle analýzu dostupný."
                ) +
                " Pro oficiální posouzení sucha konzultuj Intersucho.cz — "
                "viz docs/ADR-002-local-baseline.md a docs/ADR-006-nasa-power-rootzone.md."
            ),
        }

    def _sigma_to_moisture_pct(self, sigma_db: float, dry_db: float, wet_db: float) -> float:
        clipped = max(dry_db, min(wet_db, sigma_db))
        return (clipped - dry_db) / (wet_db - dry_db) * 100

    def _linear_trend_db(self, db_values: list[float]) -> float:
        """
        Lineární regrese přes časovou řadu — v LINEÁRNÍ škále (viz modul docstring),
        výsledek reportován jako rozdíl dB mezi fitovaným prvním a posledním bodem.
        """
        if len(db_values) < 2:
            return 0.0
        linear_values = np.array([db_to_linear(v) for v in db_values])
        x = np.arange(len(linear_values))
        slope, intercept = np.polyfit(x, linear_values, 1)
        fit_start = intercept
        fit_end = slope * (len(linear_values) - 1) + intercept
        return linear_to_db(float(fit_end)) - linear_to_db(float(fit_start))

    def _assess_drought(self, relative_moisture_pct: float) -> tuple[bool, str]:
        for threshold, label in SEVERITY_THRESHOLDS_PCT:
            if relative_moisture_pct >= threshold:
                return (label != "none"), label
        return True, "extreme"

    def _alert_message(self, severity: str, trend_db: float, reference_source: str) -> str:
        if severity == "unknown":
            return (
                "Nelze spolehlivě vyhodnotit riziko sucha — chybí dostatečná lokální "
                "historická reference pro tohle pole (reference_source=global_fallback). "
                "relative_moisture_pct níže je jen orientační odhad z globálních konstant, "
                "NENÍ to verdikt. Viz docs/ADR-002, docs/ADR-007, docs/ADR-008."
            )
        if severity == "none":
            return "Vlhkostní poměry v normě."
        direction = "vysychá" if trend_db < 0 else "vlhne"
        return f"Riziko sucha ({severity}): půda dle trendu {direction} ({trend_db:+.1f} dB)."

    def _error_response(self, code: str, message: str) -> dict:
        return {"success": False, "error_code": code, "error_message": message}
