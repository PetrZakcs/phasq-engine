"""
Copernicus DEM GLO-30 - sklon terénu. Živě ověřeno (ADR-012): CDSE
Sentinel Hub Statistical API vrací 403 (DEM není na free CDSE instanci),
funkční cesta je AWS Open Data S3 bez autentizace.

POZOR (viz engine/trafficability/classify.py docstring a ADR-013):
sklon se tady počítá a reportuje, ale NEVSTUPUJE do klasifikační logiky -
nenašel se obecný, na konkrétním stroji nezávislý literaturní práh.
"""

import math

import numpy as np
import rasterio

from engine.trafficability.models import LayerReading

BUCKET_URL = "https://copernicus-dem-30m.s3.amazonaws.com"
SOURCE_LABEL = "Copernicus DEM GLO-30 (AWS Open Data, copernicus-dem-30m)"
ATTRIBUTION = (
    "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and "
    "© Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS "
    "by the European Union and ESA; all rights reserved"
)


def _tile_name(lon: float, lat: float) -> str:
    lat_floor = math.floor(lat)
    lon_floor = math.floor(lon)
    ns = "N" if lat_floor >= 0 else "S"
    ew = "E" if lon_floor >= 0 else "W"
    lat_str = f"{ns}{abs(lat_floor):02d}_00"
    lon_str = f"{ew}{abs(lon_floor):03d}_00"
    return f"Copernicus_DSM_COG_10_{lat_str}_{lon_str}_DEM"


async def get_slope_reading(lon: float, lat: float) -> LayerReading:
    tile = _tile_name(lon, lat)
    # /vsicurl/ - GDAL čte jen potřebné okno přes HTTP range requesty (COG),
    # ne celou ~40MB dlaždici (živě ověřeno - funguje bez CDSE credentials).
    url = f"/vsicurl/{BUCKET_URL}/{tile}/{tile}.tif"

    try:
        with rasterio.open(url) as src:
            row, col = src.index(lon, lat)
            window = rasterio.windows.Window(max(col - 1, 0), max(row - 1, 0), 3, 3)
            elevation = src.read(1, window=window).astype(float)
            res_m = src.res[0] * 111_320  # stupně -> metry, hrubá aproximace na 49° severní šířky
    except rasterio.errors.RasterioIOError as e:
        return LayerReading(
            layer_name="sklon",
            value=None,
            source=SOURCE_LABEL,
            source_date=None,
            caveat=f"Nelze určit - dlaždice {tile} nedostupná ({e}).",
            data_unavailable=True,
        )

    if elevation.shape != (3, 3):
        return LayerReading(
            layer_name="sklon",
            value=None,
            source=SOURCE_LABEL,
            source_date=None,
            caveat="Nelze určit - bod je na okraji dlaždice, 3x3 okno nejde získat.",
            data_unavailable=True,
        )

    # Horn's method (standard finite-difference sklonový odhad pro 3x3 okno).
    dz_dx = ((elevation[0, 2] + 2 * elevation[1, 2] + elevation[2, 2]) -
             (elevation[0, 0] + 2 * elevation[1, 0] + elevation[2, 0])) / (8 * res_m)
    dz_dy = ((elevation[2, 0] + 2 * elevation[2, 1] + elevation[2, 2]) -
             (elevation[0, 0] + 2 * elevation[0, 1] + elevation[0, 2])) / (8 * res_m)
    slope_pct = float(np.sqrt(dz_dx**2 + dz_dy**2) * 100)

    return LayerReading(
        layer_name="sklon",
        value=round(slope_pct, 1),
        source=SOURCE_LABEL,
        source_date=None,
        caveat=(
            "Sklon je informativní, NEVSTUPUJE do klasifikace (viz ADR-013 - "
            "nenalezen obecný literaturní práh nezávislý na konkrétním stroji). "
            f"{ATTRIBUTION}"
        ),
    )
