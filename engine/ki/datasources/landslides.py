"""
Registr svahových nestabilit ČGS (sesuvy). Živě ověřeno proti
mapy.geology.cz, viz docs/ADR-009-ki-datove-zdroje.md. Licence CC BY 4.0.

Zadání kap. 4: "Pro hrozby bez doby opakování (sesuvy, poddolování)
úroveň nenavrhuj, uveď jen expozici." - ThreatFinding.probability_level
proto zůstává None, nikdy se nevolá engine.ki.scale pro tenhle zdroj.
"""

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import Point, shape

from engine.ki.datasources.arcgis_rest import ArcGisQueryError, query_layer
from engine.ki.models import ThreatFinding
from utils.reproject import utm_epsg_for_lonlat

BASE_URL = "https://mapy.geology.cz/arcgis/rest/services/Geohazardy/svahove_deformace/MapServer"
LAYER_PLOSNE = 1  # polygony - hlavní vrstva pro vzdálenostní dotaz

SOURCE_LABEL = "ČGS, Registr svahových deformací (mapy.geology.cz)"

SEARCH_BUFFER_M = 5000.0  # pokud nic v okruhu 5 km, uveď to tak

AKTIVITA_LABELS = {1: "aktivní", 2: "dočasně uklidněné", 3: "uklidněné", 10: "nezadáno"}

NAZEV_LABELS = {
    24: "propad, pseudozávrt",
    38: "výrazně zatržené břehy vodních toků a erozních rýh",
    39: "akumulační oblast",
    40: "odlučná stěna",
    41: "nestabilní rozsáhlé stavební zásahy",
    110: "nespecifikovaná svahová nestabilita",
    22: "skalní útvary",
    26: "kra (délka do 50 m)",
    1001: "řícení",
    1000: "sesouvání",
    1002: "stékání",
    1003: "povrchové ploužení",
    1004: "hlubinné ploužení",
    2000: "morfologicky zřetelné omezení",
    2001: "hypotetické omezení",
    2002: "odlučná hrana",
    2003: "spodní omezení odlučné stěny",
}


async def get_landslide_finding(lon: float, lat: float) -> tuple[ThreatFinding, list[dict]]:
    point = {"type": "Point", "coordinates": [lon, lat]}

    try:
        result = await query_layer(
            BASE_URL, LAYER_PLOSNE, point,
            distance_m=SEARCH_BUFFER_M,
        )
    except ArcGisQueryError as e:
        return ThreatFinding(
            threat_code="svahove_nestability",
            threat_label="Svahové nestability (sesuvy)",
            fact="Nelze určit - dotaz na ČGS Registr svahových deformací selhal.",
            source=SOURCE_LABEL,
            source_date=None,
            caveat=f"Chyba dotazu: {e}",
            data_unavailable=True,
        ), []

    features = result.get("features", [])

    caveat = (
        "Datum poslední aktualizace vrstvy není přes ArcGIS REST API "
        "dostupné - ověř aktuálnost přímo u ČGS. Registr obsahuje jen "
        "TERÉNNĚ OVĚŘENÉ a zdokumentované deformace - nezdokumentovaná "
        "nestabilita se zde neobjeví. Vzdálenost je od hranice polygonu "
        "deformace, ne od jeho středu."
    )

    if not features:
        return ThreatFinding(
            threat_code="svahove_nestability",
            threat_label="Svahové nestability (sesuvy)",
            fact=f"V okruhu {SEARCH_BUFFER_M:.0f} m od objektu není v registru ČGS "
                 "evidována žádná svahová deformace.",
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
    aktivita_code = props.get("aktivita")
    nazev_code = props.get("nazev")
    aktivita_text = AKTIVITA_LABELS.get(aktivita_code, f"neznámý kód ({aktivita_code})")
    nazev_text = NAZEV_LABELS.get(nazev_code, f"neznámý kód ({nazev_code})")

    inside = nearest_dist < 1.0  # prakticky uvnitř polygonu

    if inside:
        fact = f"Objekt leží v evidované svahové deformaci (typ: {nazev_text}, aktivita: {aktivita_text})."
    else:
        fact = (
            f"Nejbližší evidovaná svahová deformace je ve vzdálenosti "
            f"{nearest_dist:.0f} m (typ: {nazev_text}, aktivita: {aktivita_text})."
        )

    finding = ThreatFinding(
        threat_code="svahove_nestability",
        threat_label="Svahové nestability (sesuvy)",
        fact=fact,
        source=SOURCE_LABEL,
        source_date=None,
        caveat=caveat,
    )
    return finding, features
