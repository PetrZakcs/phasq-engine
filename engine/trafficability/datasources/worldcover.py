"""
ESA WorldCover v200 (2021) - krajinný pokryv. Živě ověřeno (ADR-012):
AWS S3, bez autentizace, dlaždice 3°×3° pojmenované podle jihozápadního
rohu zaokrouhleného dolů na násobek 3.

Třídy (živě ověřeno proti legendě, viz ADR-012/classify.py):
10 Tree cover, 20 Shrubland, 30 Grassland, 40 Cropland, 50 Built-up,
60 Bare/sparse vegetation, 70 Snow/ice, 80 Water bodies,
90 Herbaceous wetland, 95 Mangroves, 100 Moss/lichen.

POZOR: statická vrstva z 2021 (overall accuracy 76,7 % dle ESA) - není
živá, nerozpozná nedávnou změnu využití půdy (nová zástavba, odlesnění).
"""

import math

import rasterio

from engine.trafficability.models import LayerReading

BUCKET_URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"
SOURCE_LABEL = "ESA WorldCover v200 2021 (AWS Open Data, esa-worldcover)"

CLASS_NAMES = {
    10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland",
    50: "Built-up", 60: "Bare/sparse vegetation", 70: "Snow/ice",
    80: "Water bodies", 90: "Herbaceous wetland", 95: "Mangroves",
    100: "Moss/lichen",
}


def _tile_name(lon: float, lat: float) -> str:
    lat_band = math.floor(lat / 3) * 3
    lon_band = math.floor(lon / 3) * 3
    ns = "N" if lat_band >= 0 else "S"
    ew = "E" if lon_band >= 0 else "W"
    return f"ESA_WorldCover_10m_2021_v200_{ns}{abs(lat_band):02d}{ew}{abs(lon_band):03d}_Map"


async def get_land_cover_reading(lon: float, lat: float) -> LayerReading:
    tile = _tile_name(lon, lat)
    url = f"/vsicurl/{BUCKET_URL}/{tile}.tif"

    try:
        with rasterio.open(url) as src:
            row, col = src.index(lon, lat)
            window = rasterio.windows.Window(col, row, 1, 1)
            value = int(src.read(1, window=window)[0, 0])
    except rasterio.errors.RasterioIOError as e:
        return LayerReading(
            layer_name="krajinny_pokryv", value=None, source=SOURCE_LABEL, source_date=None,
            caveat=f"Nelze určit - dlaždice {tile} nedostupná ({e}).", data_unavailable=True,
        )

    class_name = CLASS_NAMES.get(value, f"neznámý kód {value}")

    return LayerReading(
        layer_name="krajinny_pokryv",
        value=value,
        source=SOURCE_LABEL,
        source_date="2021",
        caveat=(
            f"{class_name}. Statická vrstva z 2021 (overall accuracy 76,7 % dle ESA) - "
            "nedávná změna využití půdy (nová zástavba, odlesnění) by nemusela být zachycena."
        ),
    )
