"""
Poddolovaná území ČGS. Živě ověřeno proti mapy.geology.cz, viz
docs/ADR-009-ki-datove-zdroje.md. INSPIRE metadata formálně "copyright",
reálně useConstraints=noConditionsApply - viz ADR-009 pro detail.

Zadání kap. 4: "Pro hrozby bez doby opakování (sesuvy, poddolování)
úroveň nenavrhuj, uveď jen expozici." - probability_level zůstává None.
"""

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import Point, shape

from engine.ki.datasources.arcgis_rest import ArcGisQueryError, query_layer
from engine.ki.models import ThreatFinding
from utils.reproject import utm_epsg_for_lonlat

BASE_URL = "https://mapy.geology.cz/arcgis/rest/services/Dulni_Dila/poddolovana_uzemi/MapServer"
LAYER_PODDOLOVANI = 1

SOURCE_LABEL = "ČGS, Poddolovaná území (mapy.geology.cz)"

SEARCH_BUFFER_M = 2000.0


async def get_undermining_finding(lon: float, lat: float) -> tuple[ThreatFinding, list[dict]]:
    point = {"type": "Point", "coordinates": [lon, lat]}

    try:
        result = await query_layer(
            BASE_URL, LAYER_PODDOLOVANI, point,
            distance_m=SEARCH_BUFFER_M,
        )
    except ArcGisQueryError as e:
        return ThreatFinding(
            threat_code="poddolovani",
            threat_label="Poddolovaná území",
            fact="Nelze určit - dotaz na ČGS Poddolovaná území selhal.",
            source=SOURCE_LABEL,
            source_date=None,
            caveat=f"Chyba dotazu: {e}",
            data_unavailable=True,
        ), []

    features = result.get("features", [])

    caveat = (
        "Registr je založen na podkladech z let 1985-1988 (viz ČGS "
        "dokumentace) a od té doby průběžně doplňován - pro konkrétní "
        "polygon ověřuje přesné datum pole 'rok', pokud je u nálezu "
        "uvedeno. Mapuje jen historicky zdokumentovanou hlubinnou těžbu - "
        "nezdokumentovaná důlní díla se zde neobjeví."
    )

    if not features:
        return ThreatFinding(
            threat_code="poddolovani",
            threat_label="Poddolovaná území",
            fact=f"V okruhu {SEARCH_BUFFER_M:.0f} m od objektu není v registru ČGS "
                 "evidováno žádné poddolované území.",
            source=SOURCE_LABEL,
            source_date=None,
            caveat=caveat,
        ), []

    epsg = utm_epsg_for_lonlat(lon, lat)
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    point_utm = Point(transformer.transform(lon, lat))

    def _to_utm(coords: np.ndarray) -> np.ndarray:
        x, y = transformer.transform(coords[:, 0], coords[:, 1])
        return np.column_stack([x, y])

    nearest = None
    nearest_dist = float("inf")
    for feat in features:
        geom_utm = shapely.transform(shape(feat["geometry"]), _to_utm)
        dist = point_utm.distance(geom_utm)
        if dist < nearest_dist:
            nearest_dist = dist
            nearest = feat

    props = nearest.get("properties", {})
    nazev = props.get("nazev") or "neuvedeno"
    surovina = props.get("surovina") or "neuvedeno"
    rok = props.get("rok")
    source_date = str(rok) if rok else None

    inside = nearest_dist < 1.0

    if inside:
        fact = f"Objekt leží v poddolovaném území (lokalita: {nazev}, těžená surovina: {surovina})."
    else:
        fact = (
            f"Nejbližší poddolované území je ve vzdálenosti {nearest_dist:.0f} m "
            f"(lokalita: {nazev}, těžená surovina: {surovina})."
        )

    finding = ThreatFinding(
        threat_code="poddolovani",
        threat_label="Poddolovaná území",
        fact=fact,
        source=SOURCE_LABEL,
        source_date=source_date,
        caveat=caveat,
    )
    return finding, features
