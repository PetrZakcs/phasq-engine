"""
Fáze 1 spike endpoint: reálná Ïƒâ° čísla z CDSE, bez DB persistence.
Supabase integrace (status persistence, quota enforcement, audit log) je
Fáze 3 dle master_plan.md — záměrně zde chybí, ne opomenuto.
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException

from api.middleware import verify_internal_secret
from api.models import RadiometricAnalysisRequest
from engine.datasources.base import MaxAOIExceeded
from engine.datasources.nasa_power_rootzone import NasaPowerRootZoneSource, RootZoneInsufficientHistory, geometry_centroid
from engine.datasources.sentinel1_cdse import Sentinel1CDSESource
from engine.physics.baseline import HistoricalBaselineCalculator, InsufficientHistory
from engine.physics.radiometric import RadiometricAnalyzer
from utils.config import settings

router = APIRouter()


@router.post("/analyze/radiometric", dependencies=[Depends(verify_internal_secret)])
async def analyze_radiometric(req: RadiometricAnalysisRequest):
    if not settings.cdse_configured:
        raise HTTPException(
            status_code=503,
            detail="CDSE credentials nejsou nastaveny (CDSE_CLIENT_ID/CDSE_CLIENT_SECRET). "
            "Zaregistruj se na https://dataspace.copernicus.eu a vygeneruj OAuth client.",
        )

    source = Sentinel1CDSESource(
        client_id=settings.CDSE_CLIENT_ID,
        client_secret=settings.CDSE_CLIENT_SECRET,
        token_url=settings.CDSE_TOKEN_URL,
        stats_api_url=settings.CDSE_STATS_API_URL,
    )

    try:
        scenes = await source.get_scenes(
            geometry=req.geometry,
            date_start=req.date_start,
            date_end=req.date_end,
            polarizations=["VV"],
            orbit_direction=req.orbit_direction,
        )
    except MaxAOIExceeded as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"CDSE API error {e.response.status_code}: {e.response.text[:500]}",
        )

    # Lokální dry/wet baseline (viz docs/ADR-002-local-baseline.md) — bez ní
    # dává globální fallback fyzikálně chybné výsledky (ověřeno živě proti
    # Intersucho.cz). POZOR: počítá se on-demand, ~4-10s navíc na request —
    # cachování per-AOI je Fáze 3 TODO (utils/config.py, Supabase), zatím
    # zaplacena latence za správnost, ne za rychlost.
    local_reference = None
    try:
        baseline_calc = HistoricalBaselineCalculator(source)
        local_reference = await baseline_calc.compute(req.geometry, as_of_date=req.date_end)
    except InsufficientHistory:
        pass  # RadiometricAnalyzer spadne na global_fallback a označí to v response
    except httpx.HTTPStatusError:
        pass  # baseline selhala síťově - radši global_fallback než 502 na celý request

    # Nezávislý druhý zdroj pro kořenovou zónu (viz docs/ADR-006-nasa-power-rootzone.md).
    # NASA POWER, zdarma pro cokoliv, žádná registrace. Stejný fail-safe
    # vzor jako local_reference: selhání nemá shodit celý request, jen
    # o ten signál ochudit odpověď (power_reading zůstane None,
    # RadiometricAnalyzer to zohlední v measurement_caveat).
    power_reading = None
    try:
        lat, lon = geometry_centroid(req.geometry)
        power_source = NasaPowerRootZoneSource()
        power_reading = await power_source.get_root_zone_reading(lat, lon, as_of_date=req.date_end)
    except RootZoneInsufficientHistory:
        pass
    except httpx.HTTPStatusError:
        pass

    analyzer = RadiometricAnalyzer()
    result = analyzer.analyze(scenes, req.geometry, local_reference=local_reference, power_reading=power_reading)

    if result.get("success") is False:
        raise HTTPException(status_code=422, detail=result.get("error_message"))

    return result
