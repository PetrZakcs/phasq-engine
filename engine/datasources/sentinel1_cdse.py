"""
Sentinel-1 GRD přes Copernicus Data Space Ecosystem (CDSE) Sentinel Hub
Statistical API. Viz docs/ADR-001-data-source.md.

DŮLEŽITÁ POZNÁMKA K DŮVĚRYHODNOSTI TOHOTO SOUBORU:
Autentizace (OAuth2 client_credentials proti Keycloak) je standardní OIDC flow
a je zde implementována s vysokou důvěrou. Přesný JSON tvar požadavku/odpovědi
Statistical API (`_build_request_payload`, parsing v `_parse_stats_response`)
NEBYL ověřen proti živé dokumentaci ani živému volání — psáno z paměti, ne
z aktuálního zdroje pravdy. PRVNÍ ÚKOL při reálném testování (viz TODO níže):
zavolat live proti https://sh.dataspace.copernicus.eu/api/v1/statistics s
platnými credentials a opravit payload/parsing podle skutečné odpovědi.
"""

import time
from datetime import datetime, timezone

import httpx

from engine.datasources.base import DataSource, SAR_Scene, ROIStats, MaxAOIExceeded
from utils.geometry import polygon_area_ha

# MVP limit — dokud nemáme ověřené chování Statistical API na velkých AOI.
# Zvednout jen po testu na reálném velkém poli, ne odhadem.
MAX_AOI_HA = 2000.0


class Sentinel1CDSESource(DataSource):

    source_name = "sentinel1_cdse"
    typical_resolution_m = 10.0

    COLLECTION_ID = "sentinel-1-grd"

    def __init__(self, client_id: str, client_secret: str, token_url: str, stats_api_url: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_url = token_url
        self._stats_api_url = stats_api_url
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def _get_token(self) -> str:
        """OAuth2 client_credentials grant proti CDSE identity provideru (Keycloak)."""
        if self._token and time.monotonic() < self._token_expires_at - 30:
            return self._token

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
            payload = resp.json()

        self._token = payload["access_token"]
        self._token_expires_at = time.monotonic() + float(payload.get("expires_in", 300))
        return self._token

    async def get_scenes(
        self,
        geometry: dict,
        date_start: str,
        date_end: str,
        polarizations: list[str] = ["VV"],
        orbit_direction: str = "BOTH",
        **kwargs,
    ) -> list[SAR_Scene]:
        area_ha = polygon_area_ha(geometry)
        if area_ha > MAX_AOI_HA:
            raise MaxAOIExceeded(
                f"AOI {area_ha:.0f} ha přesahuje MVP limit {MAX_AOI_HA} ha pro "
                f"{self.source_name}. Zvětšit limit jen po ověřeném testu."
            )

        token = await self._get_token()
        payload = self._build_request_payload(geometry, date_start, date_end, polarizations, orbit_direction)

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                self._stats_api_url,
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            resp.raise_for_status()
            raw = resp.json()

        return self._parse_stats_response(raw, geometry, polarizations[0] if polarizations else "VV")

    async def get_scene_count(self, geometry: dict, date_start: str, date_end: str) -> int:
        scenes = await self.get_scenes(geometry, date_start, date_end)
        return len(scenes)

    def _build_request_payload(
        self, geometry: dict, date_start: str, date_end: str, polarizations: list[str], orbit_direction: str
    ) -> dict:
        # TODO(ověřit proti live API): dataFilter klíče, hodnoty polarization/
        # acquisitionMode a přesná struktura "aggregation" bloku pro Statistical API.
        evalscript = _VV_BACKSCATTER_DB_EVALSCRIPT
        return {
            "input": {
                "bounds": {
                    "geometry": geometry,
                    "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
                },
                "data": [
                    {
                        "type": self.COLLECTION_ID,
                        "dataFilter": {
                            "timeRange": {
                                "from": f"{date_start}T00:00:00Z",
                                "to": f"{date_end}T23:59:59Z",
                            },
                            "acquisitionMode": "IW",
                            **({"orbitDirection": orbit_direction} if orbit_direction != "BOTH" else {}),
                        },
                        "processing": {
                            "backCoeff": "GAMMA0_TERRAIN",
                            "orthorectify": True,
                        },
                    }
                ],
            },
            "aggregation": {
                "timeRange": {
                    "from": f"{date_start}T00:00:00Z",
                    "to": f"{date_end}T23:59:59Z",
                },
                "aggregationInterval": {"of": "P1D"},
                "evalscript": evalscript,
                "resx": self.typical_resolution_m,
                "resy": self.typical_resolution_m,
            },
        }

    def _parse_stats_response(self, raw: dict, geometry: dict, polarization: str) -> list[SAR_Scene]:
        # TODO(ověřit proti live API): skutečný tvar odpovědi. Předpoklad níže:
        # raw["data"] je list intervalů, každý má "interval"."from" a
        # "outputs"."default"."bands"."B0"."stats" s mean/stDev/percentiles.
        scenes: list[SAR_Scene] = []
        for interval in raw.get("data", []):
            stats = interval.get("outputs", {}).get("default", {}).get("bands", {}).get("B0", {}).get("stats")
            if not stats or stats.get("sampleCount", 0) == 0:
                continue

            date_str = interval["interval"]["from"][:10]
            percentiles = stats.get("percentiles", {})

            scenes.append(
                SAR_Scene(
                    acquisition_date=date_str,
                    polarization=polarization,
                    orbit_direction="UNKNOWN",  # TODO: extrahovat z metadat, pokud API vrací
                    instrument_mode="IW",
                    roi_stats=ROIStats(
                        mean_db=stats["mean"],
                        p10_db=percentiles.get("10.0", stats["mean"]),
                        p90_db=percentiles.get("90.0", stats["mean"]),
                        stddev_db=stats.get("stDev", 0.0),
                        valid_pixel_ratio=stats.get("sampleCount", 0) / max(stats.get("noDataCount", 0) + stats.get("sampleCount", 1), 1),
                    ),
                    spatial_resolution_m=self.typical_resolution_m,
                    crs="EPSG:4326",
                    bbox=_geometry_bbox(geometry),
                    source_id=f"cdse/{self.COLLECTION_ID}/{date_str}",
                    metadata={"raw_interval": interval.get("interval")},
                )
            )
        return scenes


def _geometry_bbox(geometry: dict) -> tuple:
    coords = geometry["coordinates"][0]
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return (min(lons), min(lats), max(lons), max(lats))


# evalscript v3 — VV backscatter v dB. NENÍ zde per-pixel speckle filtr
# (viz ADR-001 oprava): evaluatePixel v evalscriptu nemá garantovaný přístup
# k sousedním pixelům, takže Refined Lee kernel zde není implementován jako fakt,
# ne jen odloženo. Šum pro fázi 1 zmírňujeme přes percentily (p10/p90 v ROIStats)
# a agregaci přes více scén v RadiometricAnalyzer, ne přes filtr na vstupu.
_VV_BACKSCATTER_DB_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: ["VV", "dataMask"],
    output: [{ id: "default", bands: 1, sampleType: "FLOAT32" }]
  };
}
function evaluatePixel(samples) {
  let vv_db = samples.VV > 0 ? 10 * Math.log10(samples.VV) : -50;
  return { default: [vv_db] };
}
"""
