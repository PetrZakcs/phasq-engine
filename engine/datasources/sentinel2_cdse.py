"""
Sentinel-2 L2A NDVI přes CDSE Statistical API — vegetační hradlo pro
RadiometricAnalyzer/HistoricalBaselineCalculator (viz docs/ADR-002-local-baseline.md,
sekce "Co je skutečně potřeba k uzavření").

σ⁰ backscatter samotné neumí rozlišit "mokrá půda" od "hustá vegetace v plné
biomase" — obojí zvyšuje radarový odraz, ale z různé fyziky (dielektrická
konstanta vody vs. objemový rozptyl na listové ploše). NDVI z optického
Sentinel-2 tohle rozliší. Používáme ho k VYŘAZENÍ scén s hustou vegetací
z historické reference i z aktuální analýzy — ne k opravě čísla, k tomu,
abychom věděli, kdy číslu nevěřit.

Stejná nejistota jako u sentinel1_cdse.py: OAuth2 flow sdílený a důvěryhodný
(utils/cdse_auth.py, živě ověřený), JSON kontrakt Statistical API znovu
použitý ze stejného vzoru (živě ověřený pro S1, evalscript/SCL maskování
pro S2 NENÍ zatím živě ověřené — první test to potvrdí nebo opraví.
"""

from dataclasses import dataclass

import httpx

from utils.cdse_auth import CDSETokenProvider
from utils.reproject import reproject_geometry_to_utm

# Prahová hodnota "hustá vegetace" — NDVI nad tímhle už neplatí předpoklad
# "holá/řídce vegetovaná půda" z docstringu RadiometricAnalyzer. Konzervativní
# hodnota z literatury pro plnou vegetační pokrývku; ne vyladěno na naše pole.
DENSE_VEGETATION_NDVI_THRESHOLD = 0.35

# SCL (Scene Classification Layer) třídy, co vyřazujeme jako nespolehlivé pro NDVI:
# 0=no_data, 1=saturated/defective, 3=cloud_shadow, 8/9=cloud medium/high,
# 10=thin_cirrus, 11=snow_ice
_BAD_SCL_CLASSES = [0, 1, 3, 8, 9, 10, 11]


@dataclass
class NDVISample:
    date: str
    mean_ndvi: float
    valid_pixel_ratio: float

    def is_dense_vegetation(self, threshold: float = DENSE_VEGETATION_NDVI_THRESHOLD) -> bool:
        """
        Parametrizováno 2026-10-13 (ADR-011, engine/trafficability zadání
        fáze 0): práh 0,35 byl natvrdo a nekalibrovaný (ADR-002 to už
        tehdy přiznávalo jako "ne vyladěno na naše pole"). Výchozí hodnota
        beze změny - volající kód bez argumentu se chová přesně jako dřív.
        """
        return self.mean_ndvi > threshold


class Sentinel2NDVISource:

    COLLECTION_ID = "sentinel-2-l2a"
    typical_resolution_m = 10.0

    def __init__(self, client_id: str, client_secret: str, token_url: str, stats_api_url: str):
        self._token_provider = CDSETokenProvider.shared(client_id, client_secret, token_url)
        self._stats_api_url = stats_api_url

    async def get_ndvi_series(self, geometry: dict, date_start: str, date_end: str) -> list[NDVISample]:
        token = await self._token_provider.get_token()
        payload = self._build_request_payload(geometry, date_start, date_end)

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                self._stats_api_url,
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            resp.raise_for_status()
            raw = resp.json()

        return self._parse_stats_response(raw)

    def _build_request_payload(self, geometry: dict, date_start: str, date_end: str) -> dict:
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
                            "maxCloudCoverage": 80,  # scény nad 80% mraků rovnou přeskočit, SCL řeší zbytek
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
                "evalscript": _NDVI_EVALSCRIPT,
                "resx": self.typical_resolution_m,
                "resy": self.typical_resolution_m,
            },
        }

    def _parse_stats_response(self, raw: dict) -> list[NDVISample]:
        # Statistical API vrací "mean": "NaN" jako STRING (ne JSON null, ne
        # numerický NaN) když jsou v intervalu všechny pixely maskované
        # (typicky: malé AOI plně zakryté mrakem, i když scéna jako celek
        # prošla scéna-úrovňovým maxCloudCoverage filtrem). Živě ověřeno
        # 2026-08-30 na scéně 2026-08-17 (sampleCount == noDataCount == 5520).
        samples: list[NDVISample] = []
        for interval in raw.get("data", []):
            stats = interval.get("outputs", {}).get("default", {}).get("bands", {}).get("B0", {}).get("stats")
            if not stats or stats.get("sampleCount", 0) == 0:
                continue
            if isinstance(stats.get("mean"), str):  # "NaN" — plně maskovaný interval
                continue

            sample_count = stats.get("sampleCount", 0)
            no_data_count = stats.get("noDataCount", 0)
            if sample_count <= no_data_count:  # nic platného nezbylo po SCL masce
                continue

            date_str = interval["interval"]["from"][:10]
            valid_ratio = sample_count / max(no_data_count + sample_count, 1)
            samples.append(
                NDVISample(date=date_str, mean_ndvi=float(stats["mean"]), valid_pixel_ratio=valid_ratio)
            )
        return samples


def nearest_ndvi(ndvi_series: list[NDVISample], target_date: str, max_days_gap: int = 5) -> NDVISample | None:
    """Nejbližší NDVI vzorek k target_date (S1/S2 revizit se neshoduje den na den)."""
    from datetime import datetime

    target = datetime.strptime(target_date, "%Y-%m-%d")
    best: NDVISample | None = None
    best_gap = None
    for sample in ndvi_series:
        gap = abs((datetime.strptime(sample.date, "%Y-%m-%d") - target).days)
        if gap <= max_days_gap and (best_gap is None or gap < best_gap):
            best, best_gap = sample, gap
    return best


_NDVI_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: ["B04", "B08", "SCL", "dataMask"],
    output: [
      { id: "default", bands: 1, sampleType: "FLOAT32" },
      { id: "dataMask", bands: 1 }
    ]
  };
}
function evaluatePixel(samples) {
  let denom = samples.B08 + samples.B04;
  let ndvi = denom > 0 ? (samples.B08 - samples.B04) / denom : 0;
  let badScl = [0, 1, 3, 8, 9, 10, 11].indexOf(samples.SCL) !== -1;
  let mask = samples.dataMask * (badScl ? 0 : 1);
  return { default: [ndvi], dataMask: [mask] };
}
"""
