"""
Radiometrická analýza (vlhkost půdy) ze Sentinel-1 Ïƒâ° backscatteru.
Metoda: Change Detection (Bauer-Marschallinger et al. 2019), doi:10.3390/rs11050526

PLATÍ PRO: zemědělská půda střední Evropy, VV polarizace, IW mode,
holá/řídce vegetovaná půda. Hloubka měření ~0-5 cm (C-band).
NEPLATÍ PRO: hustá vegetace, zmrzlá půda, urbánní oblasti.

Oprava proti master_plan.md pseudokódu (chyba #2/#3 v tomtéž dokumentu, sekce 8):
ten samotný dokument varuje "průměr v dB škále je matematicky špatně", ale
referenční pseudokód (`mean_vv = np.mean(vv_values)` nad dB hodnotami) přesně
tuto chybu dělá. Tady se agreguje přes lineární škálu, viz db_to_linear/
linear_to_db a mean_backscatter_db níže.
"""

import math

import numpy as np

from engine.datasources.base import SAR_Scene

SIGMA_DRY_REF_DB = -22.0
SIGMA_WET_REF_DB = -8.0
DROUGHT_THRESHOLD_DB = -17.0

MIN_VALID_PIXEL_RATIO = 0.5  # scéna s méně platnými pixely v AOI se zahazuje


def db_to_linear(db: float) -> float:
    return 10 ** (db / 10.0)


def linear_to_db(linear: float) -> float:
    if linear <= 0:
        return -50.0
    return 10 * math.log10(linear)


def mean_backscatter_db(db_values: list[float]) -> float:
    """Průměr přes VÍCE scén musí jít přes lineární škálu, ne přímo v dB."""
    if not db_values:
        return 0.0
    linear_values = [db_to_linear(v) for v in db_values]
    return linear_to_db(float(np.mean(linear_values)))


class RadiometricAnalyzer:

    def analyze(self, scenes: list[SAR_Scene], roi_geometry: dict) -> dict:
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
        relative_moisture = self._sigma_to_moisture_pct(mean_vv)
        drought_risk, severity = self._assess_drought(mean_vv, trend_db)

        return {
            "success": True,
            "analysis_type": "radiometric",
            "data_source": valid_scenes[0].source_id.split("/")[0],
            "scenes_count": len(valid_scenes),
            "scenes_dropped_low_coverage": dropped,
            "mean_backscatter_vv_db": round(mean_vv, 2),
            "relative_moisture_pct": round(relative_moisture, 1),
            "trend_db": round(trend_db, 2),
            "drought_risk": drought_risk,
            "drought_severity": severity,
            "alert_message": self._alert_message(severity, trend_db),
            "timeseries": timeseries,
            "methodology": "change_detection",
            "reference_dry_db": SIGMA_DRY_REF_DB,
            "reference_wet_db": SIGMA_WET_REF_DB,
            "drought_threshold_db": DROUGHT_THRESHOLD_DB,
            "citation": "Bauer-Marschallinger et al. (2019), doi:10.3390/rs11050526",
            "spatial_resolution_m": valid_scenes[0].spatial_resolution_m,
        }

    def _sigma_to_moisture_pct(self, sigma_db: float) -> float:
        clipped = max(SIGMA_DRY_REF_DB, min(SIGMA_WET_REF_DB, sigma_db))
        return (clipped - SIGMA_DRY_REF_DB) / (SIGMA_WET_REF_DB - SIGMA_DRY_REF_DB) * 100

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

    def _assess_drought(self, mean_vv: float, trend_db: float) -> tuple[bool, str]:
        if mean_vv > -12.0:
            return False, "none"
        elif mean_vv > -14.0:
            return False, "mild"
        elif mean_vv > DROUGHT_THRESHOLD_DB:
            return True, "moderate"
        elif mean_vv > -19.0:
            return True, "severe"
        else:
            return True, "extreme"

    def _alert_message(self, severity: str, trend_db: float) -> str:
        if severity == "none":
            return "Vlhkostní poměry v normě."
        direction = "vysychá" if trend_db < 0 else "vlhne"
        return f"Riziko sucha ({severity}): půda dle trendu {direction} ({trend_db:+.1f} dB)."

    def _error_response(self, code: str, message: str) -> dict:
        return {"success": False, "error_code": code, "error_message": message}
