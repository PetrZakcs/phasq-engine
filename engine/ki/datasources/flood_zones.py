"""
Návrhové záplavové území (Q5/Q20/Q100) - VÚV TGM, ISVS Voda.
Živě ověřeno proti ags.vuv.cz, viz docs/ADR-009-ki-datove-zdroje.md.
Starý endpoint ags.vuv.cz/zu/q je mrtvý (service not started) - tohle
je živý nástupce nalezený přes voda.gov.cz.
"""

from engine.ki.datasources.arcgis_rest import ArcGisQueryError, query_layer
from engine.ki.models import ThreatFinding
from engine.ki.scale import propose_flood_probability

BASE_URL = "https://ags.vuv.cz/arcgis/rest/services/isvs_voda/isvs_voda/MapServer"
LAYER_AKTIVNI_ZONA = 11
LAYER_Q500 = 12
LAYER_Q100 = 13
LAYER_Q20 = 14
LAYER_Q5 = 15

SOURCE_LABEL = "VÚV TGM, ISVS Voda (ags.vuv.cz/arcgis/rest/services/isvs_voda)"


async def get_flood_finding(lon: float, lat: float) -> tuple[ThreatFinding, list[dict]]:
    point = {"type": "Point", "coordinates": [lon, lat]}

    try:
        q5 = await query_layer(BASE_URL, LAYER_Q5, point)
        q20 = await query_layer(BASE_URL, LAYER_Q20, point)
        q100 = await query_layer(BASE_URL, LAYER_Q100, point)
        aktivni = await query_layer(BASE_URL, LAYER_AKTIVNI_ZONA, point)
        q500 = await query_layer(BASE_URL, LAYER_Q500, point)
    except ArcGisQueryError as e:
        return ThreatFinding(
            threat_code="povodne_navrhove",
            threat_label="Povodně (návrhové záplavové území)",
            fact="Nelze určit - dotaz na VÚV ISVS Voda selhal.",
            source=SOURCE_LABEL,
            source_date=None,
            caveat=f"Chyba dotazu: {e}",
            data_unavailable=True,
        ), []

    in_q5 = len(q5.get("features", [])) > 0
    in_q20 = len(q20.get("features", [])) > 0
    in_q100 = len(q100.get("features", [])) > 0
    in_aktivni = len(aktivni.get("features", [])) > 0
    in_q500 = len(q500.get("features", [])) > 0

    proposal = propose_flood_probability(in_q5=in_q5, in_q20=in_q20, in_q100=in_q100)

    fact_parts = []
    if in_q5:
        fact_parts.append("Objekt leží v záplavovém území Q5.")
    elif in_q20:
        fact_parts.append("Objekt leží v záplavovém území Q20 (mimo Q5).")
    elif in_q100:
        fact_parts.append("Objekt leží v záplavovém území Q100 (mimo Q20).")
    else:
        fact_parts.append("Objekt leží mimo vymezená záplavová území Q5/Q20/Q100.")

    if in_aktivni:
        fact_parts.append(
            "Objekt leží v aktivní zóně záplavového území - dle § 67 vodního "
            "zákona je zde zakázána výstavba (s výjimkami)."
        )
    if in_q500 and not in_q100:
        fact_parts.append("Objekt leží v záplavovém území Q500 (mimo Q100) - doplňující informace, "
                           "tabulka č. 1 vyhlášky Q500 explicitně nedefinuje.")

    caveat = (
        "Datum poslední aktualizace vrstvy není přes ArcGIS REST API "
        "dostupné (pole editingInfo chybí) - ověř aktuálnost přímo u VÚV "
        "TGM před finálním použitím. Zdroj nerozlišuje typ vodního toku "
        "ani ochranu protipovodňovými opatřeními vybudovanými po "
        "zpracování podkladu."
    )

    finding = ThreatFinding(
        threat_code="povodne_navrhove",
        threat_label="Povodně (návrhové záplavové území)",
        fact=" ".join(fact_parts),
        source=SOURCE_LABEL,
        source_date=None,
        caveat=caveat,
        probability_level=proposal.level,
        probability_label=proposal.label,
        is_borderline=proposal.is_borderline,
        borderline_alternative_level=proposal.borderline_alternative_level,
        borderline_alternative_label=proposal.borderline_alternative_label,
        rationale=proposal.rationale,
    )
    raw_features = q5.get("features", []) + q20.get("features", []) + q100.get("features", [])
    return finding, raw_features
