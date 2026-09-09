"""
Sentinel-2 true-color náhledový snímek pro AOI — přes CDSE/Sentinel Hub
Process API (jiné volání než Statistical API v sentinel1_cdse.py — Process
API vrací obrázek/raster, ne agregovanou statistiku).

PROČ TOHLE EXISTUJE (2026-09-09): appka dřív používala Esri World_Imagery
dlaždice jako mapový podklad — živě ověřeno, že to Esri explicitně
zakazuje pro komerční použití bez ArcGIS licence (viz docs/ADR-005).
NASA GIBS je zdarma, ale rozlišení (~250m-1km) je pro pole o pár set
metrů nepoužitelné. Tohle je 10m rozlišení, stejná CDSE licence, co už
máme pro fyziku — žádná nová externí závislost k ověřování.

Živě ověřeno 2026-09-09: funkční napoprvé, reálný snímek (viditelná
struktura pole, ne prázdný/černý obrázek).
"""

import httpx

from utils.reproject import reproject_geometry_to_utm

PROCESS_API_URL_SUFFIX = "process"  # sdílí base URL se Statistical API, jiná cesta

MAX_DIMENSION_PX = 512  # strop na velikost obrázku - cena/rychlost, ne kvalita

_TRUE_COLOR_EVALSCRIPT = """//VERSION=3
function setup() {
  return { input: ["B02", "B03", "B04"], output: { bands: 3, sampleType: "AUTO" } };
}
function evaluatePixel(sample) {
  return [sample.B04 * 2.5, sample.B03 * 2.5, sample.B02 * 2.5];
}"""


class Sentinel2TrueColorSource:
    def __init__(self, client_id: str, client_secret: str, token_url: str, stats_api_url: str):
        # Sdílí OAuth flow se Sentinel1CDSESource, ale je to samostatná
        # instance - jednodušší než sdílet token cache napříč zdroji teď,
        # cena je jeden extra token request, ne architektonický problém.
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_url = token_url
        # stats_api_url je tvaru .../api/v1/statistics - process API je na .../api/v1/process
        self._process_api_url = stats_api_url.rsplit("/", 1)[0] + "/" + PROCESS_API_URL_SUFFIX

    async def _get_token(self) -> str:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                self._token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            resp.raise_for_status()
            return resp.json()["access_token"]

    async def get_truecolor_png(self, geometry: dict, date_start: str, date_end: str) -> bytes:
        token = await self._get_token()
        utm_geometry, epsg = reproject_geometry_to_utm(geometry)
        width, height = self._aspect_correct_dimensions(utm_geometry)

        payload = {
            "input": {
                "bounds": {
                    "geometry": utm_geometry,
                    "properties": {"crs": f"http://www.opengis.net/def/crs/EPSG/0/{epsg}"},
                },
                "data": [
                    {
                        "type": "sentinel-2-l2a",
                        "dataFilter": {
                            "timeRange": {"from": f"{date_start}T00:00:00Z", "to": f"{date_end}T23:59:59Z"},
                            "mosaickingOrder": "leastCC",  # nejmíň zamračená dostupná scéna v okně
                        },
                    }
                ],
            },
            "output": {
                "width": width,
                "height": height,
                "responses": [{"identifier": "default", "format": {"type": "image/png"}}],
            },
            "evalscript": _TRUE_COLOR_EVALSCRIPT,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(self._process_api_url, headers={"Authorization": f"Bearer {token}"}, json=payload)
            resp.raise_for_status()
            return resp.content

    def _aspect_correct_dimensions(self, utm_geometry: dict) -> tuple[int, int]:
        """Zabraňuje zkreslení obrázku, když AOI bbox není čtvercové."""
        coords = utm_geometry["coordinates"][0]
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        width_m = max(xs) - min(xs)
        height_m = max(ys) - min(ys)
        if width_m <= 0 or height_m <= 0:
            return MAX_DIMENSION_PX, MAX_DIMENSION_PX

        if width_m >= height_m:
            width = MAX_DIMENSION_PX
            height = max(64, round(MAX_DIMENSION_PX * height_m / width_m))
        else:
            height = MAX_DIMENSION_PX
            width = max(64, round(MAX_DIMENSION_PX * width_m / height_m))
        return width, height
