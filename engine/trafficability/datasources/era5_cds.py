"""
ERA5-Land (CDS) - objemová vlhkost 0-7cm (volumetric_soil_water_layer_1).

Živě ověřeno (ADR-012): CDS (cds.climate.copernicus.eu) je SAMOSTATNÁ
platforma, ne CDSE - vlastní ECMWF účet a CDS_API_KEY. I s platným
klíčem je navíc nutné ODSOUHLASIT LICENCI datasetu na webu (ne přes
API) - živě ověřeno 2026-10-13: platný klíč, ale dotaz spadl na
`403 required licences not accepted`, dokud se licence neodsouhlasí na
https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land?tab=download#manage-licences

Oficiální REST API je podle vlastní dokumentace CDS "not supported pro
pokročilé uživatele" - použit `cdsapi` (oficiální doporučená knihovna),
ne přímé HTTP volání jako u ostatních zdrojů v tomhle projektu.
`cdsapi.Client` je SYNCHRONNÍ (blokující síťové volání + polling), proto
obalený v `asyncio.to_thread`, aby neblokoval event loop.

I po získání dat platí limit z ADR-012: finální ERA5-Land produkt je
2-3 měsíce starý. NRT varianta (ERA5-Land-T) tímhle klientem není
cíleně vybíraná - `reanalysis-era5-land` dataset vrací finální produkt.
"""

import asyncio
import io
import os
from datetime import datetime, timedelta

import numpy as np
import rasterio

from engine.trafficability.models import LayerReading

SOURCE_LABEL = "ERA5-Land (Climate Data Store, cds.climate.copernicus.eu)"
CDS_API_URL = "https://cds.climate.copernicus.eu/api"
FINAL_PRODUCT_LAG_DAYS = 60  # konzervativní odhad ze zadání ("2-3 měsíce"), ADR-012


def _retrieve_sync(api_key: str, lat: float, lon: float, target_date: datetime) -> bytes:
    import cdsapi

    client = cdsapi.Client(url=CDS_API_URL, key=api_key, quiet=True)
    buf = io.BytesIO()
    request = {
        "variable": ["volumetric_soil_water_layer_1"],
        "year": f"{target_date.year:04d}",
        "month": f"{target_date.month:02d}",
        "day": [f"{target_date.day:02d}"],
        "time": ["12:00"],
        "data_format": "netcdf",
        "download_format": "unarchived",
        # N, W, S, E - malé okno kolem bodu, SoilGrids stejný vzor
        "area": [lat + 0.05, lon - 0.05, lat - 0.05, lon + 0.05],
    }
    result = client.retrieve("reanalysis-era5-land", request)
    tmp_path = "/tmp/_era5_land_tmp.nc"
    result.download(tmp_path)
    with open(tmp_path, "rb") as f:
        return f.read()


async def get_volumetric_moisture_reading(lon: float, lat: float, as_of_date: str | None = None) -> LayerReading:
    token = os.environ.get("CDS_API_KEY")

    if not token:
        return LayerReading(
            layer_name="objemova_vlhkost_0_7cm", value=None, source=SOURCE_LABEL, source_date=None,
            caveat=(
                "Chybí CDS_API_KEY. ERA5-Land vyžaduje samostatnou registraci "
                "na cds.climate.copernicus.eu (CDSE credentials nestačí) - viz "
                "docs/ADR-012-pruchodnost-datove-zdroje.md."
            ),
            data_unavailable=True,
        )

    as_of = datetime.strptime(as_of_date, "%Y-%m-%d") if as_of_date else datetime.now()
    # Finální produkt má ~2-3 měsíční latenci (ADR-012, ze zadání) - cílíme
    # na nejnovější pravděpodobně dostupný měsíc, ne na as_of_date samotné.
    target = as_of - timedelta(days=FINAL_PRODUCT_LAG_DAYS)

    try:
        raw = await asyncio.to_thread(_retrieve_sync, token, lat, lon, target)
    except Exception as e:
        return LayerReading(
            layer_name="objemova_vlhkost_0_7cm", value=None, source=SOURCE_LABEL, source_date=None,
            caveat=(
                f"Nelze určit - dotaz na CDS selhal ({type(e).__name__}: {e}). "
                "Pokud jde o 'required licences not accepted', je nutné odsouhlasit "
                "licenci na https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land"
                "?tab=download#manage-licences (jen přes web, ne přes API)."
            ),
            data_unavailable=True,
        )

    with rasterio.open(io.BytesIO(raw)) as src:
        data = src.read(1).astype(float)
    valid = data[~np.isnan(data)]
    if valid.size == 0:
        return LayerReading(
            layer_name="objemova_vlhkost_0_7cm", value=None, source=SOURCE_LABEL, source_date=None,
            caveat="Nelze určit - staženo, ale žádná platná data v okně kolem bodu.",
            data_unavailable=True,
        )

    vol_moisture = float(valid.mean())
    lag_days = (as_of - target).days

    return LayerReading(
        layer_name="objemova_vlhkost_0_7cm",
        value=round(vol_moisture, 3),
        source=SOURCE_LABEL,
        source_date=target.strftime("%Y-%m-%d"),
        caveat=(
            f"m3/m3, finální (kvalitně ověřený) produkt, ~{lag_days} dní staré "
            "(ADR-012: ERA5-Land finální produkt má 2-3měsíční latenci) - "
            "NENÍ aktuální stav, jen sezónní/klimatologický kontext."
        ),
    )
