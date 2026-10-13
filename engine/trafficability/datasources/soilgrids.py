"""
SoilGrids (ISRIC) - obsah jílu v povrchové vrstvě (0-5cm). Živě ověřeno
(ADR-012): REST API je mrtvé (ISRIC to sama přiznává), WCS funguje.

Souřadnicový systém je Interrupted Goode Homolosine (IGH) - ISRIC ho
sám značí jako "EPSG:152160", ale to NENÍ platný EPSG kód v pyproj
databázi (živě ověřeno - CRSError). Funkční cesta: proj4 string přímo
('+proj=igh ...'), ne EPSG lookup. BEZ týhle opravy by dotaz tiše vrátil
data ze ŠPATNÉ lokace (žádná chyba, jen jiné místo) - první pokus s
hádaným IGH offsetem tohle přesně udělal, odhaleno jen srovnáním s
properly transformovanou hodnotou.

Konverzní faktor: SoilGrids v2.0 vrací clay v g/kg, dělit 10 pro
procenta (g/100g) - viz ADR-012 pro zdroje.
"""

import numpy as np
import rasterio
import httpx
from pyproj import CRS, Transformer

from engine.trafficability.models import LayerReading

_IGH = CRS.from_proj4("+proj=igh +lat_0=0 +lon_0=0 +datum=WGS84 +units=m +no_defs")
_TO_IGH = Transformer.from_crs("EPSG:4326", _IGH, always_xy=True)

WCS_URL = "https://maps.isric.org/mapserv"
COVERAGE_ID = "clay_0-5cm_mean"
SOURCE_LABEL = "SoilGrids (ISRIC), clay_0-5cm_mean (maps.isric.org WCS)"

BUFFER_M = 250.0  # polovina strany čtverce kolem bodu, SoilGrids je 250m rozlišení - jeden pixel


async def get_clay_reading(lon: float, lat: float) -> LayerReading:
    x, y = _TO_IGH.transform(lon, lat)
    params = {
        "map": "/map/clay.map",
        "SERVICE": "WCS", "VERSION": "2.0.1", "REQUEST": "GetCoverage",
        "COVERAGEID": COVERAGE_ID, "FORMAT": "image/tiff",
        "SUBSET": [f"X({x - BUFFER_M},{x + BUFFER_M})", f"Y({y - BUFFER_M},{y + BUFFER_M})"],
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(WCS_URL, params=params)
            resp.raise_for_status()
            raw = resp.content
    except httpx.HTTPStatusError as e:
        return LayerReading(
            layer_name="jil_pct", value=None, source=SOURCE_LABEL, source_date=None,
            caveat=f"Nelze určit - WCS dotaz selhal ({e}).", data_unavailable=True,
        )

    import io
    with rasterio.open(io.BytesIO(raw)) as src:
        data = src.read(1).astype(float)

    valid = data[data > 0]
    if valid.size == 0:
        return LayerReading(
            layer_name="jil_pct", value=None, source=SOURCE_LABEL, source_date=None,
            caveat="Nelze určit - žádná platná data v okně kolem bodu (nodata/okraj dlaždice).",
            data_unavailable=True,
        )

    clay_pct = float(valid.mean()) / 10.0

    return LayerReading(
        layer_name="jil_pct",
        value=round(clay_pct, 1),
        source=SOURCE_LABEL,
        source_date=None,
        caveat="SoilGrids verze 2.0 (2020), statická vrstva - půdní textura se mezi vydáními nemění rychle, ale není živá.",
    )
