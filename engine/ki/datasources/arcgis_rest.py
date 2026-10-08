"""
Generický klient pro ArcGIS REST MapServer query endpoint. Sdílený vzor
pro VÚV (záplavová území) a ČGS (sesuvy, poddolování) - obě instituce
publikují data přes stejné ArcGIS Server REST rozhraní, živě ověřeno
proti oběma, viz docs/ADR-009-ki-datove-zdroje.md.

POZNÁMKA K DATU AKTUALIZACE: žádná z těchto služeb nevrací v odpovědi
`editingInfo`/datum poslední editace (ověřeno živě, pole je `None` u
obou). Nelze tedy programaticky zjistit přesné datum poslední aktualizace
vrstvy - report u každého nálezu uvádí "datum aktualizace není v API
dostupné" místo smyšleného data (zadání pravidlo 1).
"""

import json

import httpx


class ArcGisQueryError(Exception):
    pass


def _to_esri_geometry(geometry: dict) -> tuple[str, str]:
    if geometry["type"] == "Point":
        lon, lat = geometry["coordinates"]
        return (
            json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}),
            "esriGeometryPoint",
        )
    if geometry["type"] == "Polygon":
        return (
            json.dumps({"rings": geometry["coordinates"], "spatialReference": {"wkid": 4326}}),
            "esriGeometryPolygon",
        )
    raise ValueError(f"Nepodporovaný typ geometrie pro ArcGIS REST dotaz: {geometry['type']}")


async def query_layer(
    base_url: str,
    layer_id: int,
    geometry: dict,
    *,
    spatial_rel: str = "esriSpatialRelIntersects",
    out_fields: str = "*",
    distance_m: float | None = None,
    timeout: float = 20.0,
) -> dict:
    """
    Vrátí GeoJSON FeatureCollection z ArcGIS REST /query endpointu.
    `distance_m` (s spatial_rel=esriSpatialRelIntersects) rozšíří dotaz
    o buffer o zadaný počet metrů - použito pro "nejbližší prvek do X m"
    dotazy (sesuvy, poddolování), kde přímý point-in-polygon test nestačí.
    """
    url = f"{base_url}/{layer_id}/query"
    esri_geom, geom_type = _to_esri_geometry(geometry)

    params = {
        "f": "geojson",
        "geometry": esri_geom,
        "geometryType": geom_type,
        "inSR": "4326",
        "outSR": "4326",
        "spatialRel": spatial_rel,
        "outFields": out_fields,
        "returnGeometry": "true",
    }
    if distance_m is not None:
        params["distance"] = distance_m
        params["units"] = "esriSRUnit_Meter"

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    if isinstance(data, dict) and "error" in data:
        raise ArcGisQueryError(f"{base_url}/{layer_id}: {data['error']}")

    return data
