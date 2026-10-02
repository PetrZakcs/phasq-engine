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

import httpx

from engine.datasources.base import DataSource, SAR_Scene, ROIStats, MaxAOIExceeded
from utils.cdse_auth import CDSETokenProvider
from utils.decibel import linear_to_db, approx_stddev_db
from utils.geometry import polygon_area_ha
from utils.reproject import reproject_geometry_to_utm

# MVP limit — dokud nemáme ověřené chování Statistical API na velkých AOI.
# Zvednout jen po testu na reálném velkém poli, ne odhadem.
MAX_AOI_HA = 2000.0


class Sentinel1CDSESource(DataSource):

    source_name = "sentinel1_cdse"
    typical_resolution_m = 10.0

    COLLECTION_ID = "sentinel-1-grd"

    def __init__(self, client_id: str, client_secret: str, token_url: str, stats_api_url: str):
        self._token_provider = CDSETokenProvider(client_id, client_secret, token_url)
        self._stats_api_url = stats_api_url

    async def _get_token(self) -> str:
        return await self._token_provider.get_token()

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

        band = polarizations[0] if polarizations else "VV"
        token = await self._get_token()
        payload = self._build_request_payload(geometry, date_start, date_end, band, orbit_direction)

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                self._stats_api_url,
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            resp.raise_for_status()
            raw = resp.json()

        return self._parse_stats_response(raw, geometry, band, orbit_direction)

    async def get_scene_count(self, geometry: dict, date_start: str, date_end: str) -> int:
        scenes = await self.get_scenes(geometry, date_start, date_end)
        return len(scenes)

    def _build_request_payload(
        self, geometry: dict, date_start: str, date_end: str, band: str, orbit_direction: str
    ) -> dict:
        # Bounds musí být v metrickém CRS — resx/resy jsou v jednotkách bounds
        # CRS. Ověřeno živě 2026-08-30: s EPSG:4326 (stupně) a resx=10 spadne
        # celé AOI do jednoho pixelu (sampleCount=1). Viz utils/reproject.py.
        utm_geometry, epsg = reproject_geometry_to_utm(geometry)

        return {
            "input": {
                "bounds": {
                    "geometry": utm_geometry,
                    "properties": {"crs": f"http://www.opengis.net/def/crs/EPSG/0/{epsg}"},
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
                "evalscript": _backscatter_linear_evalscript(band),
                "resx": self.typical_resolution_m,
                "resy": self.typical_resolution_m,
            },
            "calculations": {
                "default": {
                    "statistics": {
                        "default": {
                            "percentiles": {"k": [10, 90], "smoothed": False}
                        }
                    }
                }
            },
        }

    def _parse_stats_response(
        self, raw: dict, geometry: dict, polarization: str, orbit_direction: str = "BOTH"
    ) -> list[SAR_Scene]:
        # Oprava 2026-10-01 (nález z externí review, živě ověřeno):
        # evalscript teď vrací LINEÁRNÍ hodnoty, ne dB — server agreguje
        # (mean/percentily) LINEÁRNĚ, dB převod je AŽ TADY, po agregaci.
        # Opačný postup (dB per-pixel, server zprůměruje dB) dával živě
        # ověřeno o 0,624 dB jinou hodnotu — stejná chyba jako #3
        # z master_plan.md (průměr v dB škále), jen prostorově přes
        # pixely místo časově přes scény.
        #
        # valid_pixel_ratio: geometryPixelCount je TOP-LEVEL pole v
        # odpovědi (ne per-interval) — živě ověřeno, že je konstantní
        # napříč scénami pro danou AOI (čistě geometrický údaj: kolik
        # pixelů polygon skutečně pokrývá). sampleCount je podle
        # dokumentace Sentinel Hub počet pixelů v BOUNDING BOXU geometrie,
        # ne v polygonu — dělit jím měří hlavně tvar pole vůči jeho
        # obdélníkovému obalu, ne kvalitu dat. Správný poměr:
        # (sampleCount - noDataCount) / geometryPixelCount.
        geometry_pixel_count = raw.get("geometryPixelCount")

        scenes: list[SAR_Scene] = []
        for interval in raw.get("data", []):
            stats = interval.get("outputs", {}).get("default", {}).get("bands", {}).get("B0", {}).get("stats")
            if not stats or stats.get("sampleCount", 0) == 0:
                continue

            date_str = interval["interval"]["from"][:10]
            percentiles = stats.get("percentiles", {})

            mean_linear = stats["mean"]
            mean_db = linear_to_db(mean_linear)
            p10_db = linear_to_db(percentiles.get("10.0", mean_linear))
            p90_db = linear_to_db(percentiles.get("90.0", mean_linear))

            sample_count = stats.get("sampleCount", 0)
            no_data_count = stats.get("noDataCount", 0)
            valid_in_polygon = max(sample_count - no_data_count, 0)
            if geometry_pixel_count:
                valid_ratio = valid_in_polygon / geometry_pixel_count
            else:
                # geometryPixelCount chybí (nečekané) - fallback na starou
                # aproximaci, radši konzervativní odhad než pád na chybě.
                valid_ratio = valid_in_polygon / max(sample_count, 1)

            # Statistical API nevrací per-scéna orbitDirection v odpovědi
            # (ověřeno čtením dokumentace, ne nalezeno žádné takové pole).
            # Když request explicitně filtroval na ASCENDING/DESCENDING,
            # KAŽDÁ vrácená scéna tomu filtru nutně vyhovuje - víme to jistě,
            # ne hádáme. Jen při "BOTH" nejde rozlišit bez dalšího volání,
            # proto zůstává "UNKNOWN" (čestně, ne smyšlená hodnota).
            scene_orbit = orbit_direction if orbit_direction != "BOTH" else "UNKNOWN"
            scenes.append(
                SAR_Scene(
                    acquisition_date=date_str,
                    polarization=polarization,
                    orbit_direction=scene_orbit,
                    instrument_mode="IW",
                    roi_stats=ROIStats(
                        mean_db=mean_db,
                        p10_db=p10_db,
                        p90_db=p90_db,
                        stddev_db=approx_stddev_db(stats.get("stDev", 0.0), mean_linear),
                        valid_pixel_ratio=valid_ratio,
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


# evalscript v3 — backscatter v LINEÁRNÍ škále (NE dB) pro zadanou
# polarizaci (VV/VH). Oprava 2026-10-01: dřív se dB počítalo tady, per
# pixel, a Statistical API pak server-side ZPRŮMĚROVALO ty dB hodnoty —
# matematicky stejná chyba jako #3 z master_plan.md (průměr v dB škále),
# jen prostorově přes pixely místo časově přes scény. Živě ověřeno:
# rozdíl 0,624 dB proti správnému postupu (zprůměrovat lineárně, pak
# převést na dB — viz _parse_stats_response). Evalscript proto vrací
# syrovou lineární hodnotu, dB převod je až po agregaci v Pythonu.
#
# NENÍ zde per-pixel speckle filtr (viz ADR-001 oprava): evaluatePixel
# v evalscriptu nemá garantovaný přístup k sousedním pixelům, takže
# Refined Lee kernel zde není implementován jako fakt, ne jen odloženo.
# Šum pro fázi 1 zmírňujeme přes percentily (p10/p90 v ROIStats) a
# agregaci přes více scén v RadiometricAnalyzer, ne přes filtr na vstupu.
def _backscatter_linear_evalscript(band: str) -> str:
    return f"""
//VERSION=3
function setup() {{
  return {{
    input: ["{band}", "dataMask"],
    output: [
      {{ id: "default", bands: 1, sampleType: "FLOAT32" }},
      {{ id: "dataMask", bands: 1 }}
    ]
  }};
}}
function evaluatePixel(samples) {{
  return {{ default: [samples.{band}], dataMask: [samples.dataMask] }};
}}
"""
