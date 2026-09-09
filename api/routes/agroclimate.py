"""
Fáze B "dokončovacího" plánu pro zemědělský vertikál (viz docs/ADR-004-agroclimate.md).
Agroklimatické indexy z NASA POWER (viz ADR-005 — přepnuto z Open-Meteo,
který není zdarma pro komerční použití). Žádná CDSE závislost, žádná
autentizace navíc.
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException

from api.middleware import verify_internal_secret
from api.models import AgroclimateRequest
from engine.datasources.nasa_power_rootzone import geometry_centroid
from engine.datasources.nasa_power_weather import NasaPowerWeatherSource
from engine.physics.agroclimate import (
    compute_gdd,
    find_last_spring_frost,
    find_first_autumn_frost,
    compute_precipitation_deficit_mm,
    historical_daily_precip_mean,
)

router = APIRouter()


@router.post("/agroclimate/summary", dependencies=[Depends(verify_internal_secret)])
async def agroclimate_summary(req: AgroclimateRequest):
    lat, lon = geometry_centroid(req.geometry)
    source = NasaPowerWeatherSource()
    as_of_year = int(req.as_of_date[:4])

    try:
        current = await source.get_daily_weather(lat, lon, req.season_start, req.as_of_date)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"NASA POWER error {e.response.status_code}")

    if not current.dates:
        raise HTTPException(status_code=422, detail="Žádná data pro zadané období.")

    # NASA POWER má ~9-10denní zpoždění (MERRA-2 reanalýza) — poslední dny
    # requestovaného období se zahazují jako chybějící (nasa_power_weather.py).
    # data_through_date říká, kam GDD/mráz/srážky SKUTEČNĚ sahají — jinak
    # by uživatel mohl zaměnit "GDD do dneška" za "GDD do před 10 dny".
    data_through_date = current.dates[-1]

    gdd = compute_gdd(current.tmax, current.tmin, base_temp=req.gdd_base_temp)
    last_spring_frost = find_last_spring_frost(current.dates, current.tmin)
    first_autumn_frost = find_first_autumn_frost(current.dates, current.tmin)

    hist_start = f"{as_of_year - req.lookback_years}-01-01"
    hist_end = f"{as_of_year - 1}-12-31"
    try:
        historical = await source.get_daily_weather(lat, lon, hist_start, hist_end)
        hist_mean = historical_daily_precip_mean(historical.dates, historical.precipitation_mm, years_exclude={as_of_year})
        precip_deficit_mm = compute_precipitation_deficit_mm(current.precipitation_mm, hist_mean)
    except (httpx.HTTPStatusError, ValueError):
        hist_mean = None
        precip_deficit_mm = None

    return {
        "success": True,
        "season_start": req.season_start,
        "as_of_date": req.as_of_date,
        "data_through_date": data_through_date,
        "days_in_period": len(current.dates),
        "growing_degree_days": gdd,
        "gdd_base_temp": req.gdd_base_temp,
        "last_spring_frost": last_spring_frost,
        "first_autumn_frost": first_autumn_frost,
        "precipitation_deficit_mm": precip_deficit_mm,
        "historical_daily_precip_mean_mm": round(hist_mean, 2) if hist_mean is not None else None,
        "historical_lookback_years": req.lookback_years,
        "data_source": "nasa_power_merra2",
        "methodology": "gdd_mcmaster_wilhelm_1997",
        "caveat": (
            "gdd_base_temp je defaultní hodnota pro obiloviny střední Evropy, NE "
            "univerzální fyzikální konstanta — pro kukuřici/slunečnici použij vyšší "
            "základní teplotu (~10°C). Data jsou z ~50km rozlišení reanalýzy (MERRA-2), "
            "ne z meteostanice na poli. NASA POWER má ~9-10denní zpoždění — "
            "'data_through_date' říká, kam čísla skutečně sahají, ne 'as_of_date'."
        ),
    }
