"""
GeoPackage výstup - objekty, jejich výsledky a podkladové vrstvy použité
k výpočtu (zadání kap. 2: "GeoPackage se všemi použitými vrstvami a
výsledky").
"""

from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point, shape

from engine.ki.models import ObjectReport


def write_geopackage(reports: list[ObjectReport], raw_layers: dict, out_path: Path) -> None:
    """
    `raw_layers`: {"zaplavova_uzemi": [geojson features...], "svahove_nestability": [...], "poddolovani": [...]}
    skutečně stažené podkladové vrstvy z ADR-009 zdrojů, pro dohledatelnost v GIS.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    # Vrstva objektů
    obj_rows = [
        {"id": r.obj.id, "name": r.obj.name, "source_note": r.obj.source_note, "geometry": Point(r.obj.lon, r.obj.lat)}
        for r in reports
    ]
    gpd.GeoDataFrame(obj_rows, crs="EPSG:4326").to_file(out_path, layer="objekty", driver="GPKG")

    # Vrstva výsledků (jeden bod na objekt+hrozba, atributy = ThreatFinding)
    finding_rows = []
    for r in reports:
        for f in r.findings:
            finding_rows.append({
                "objekt_id": r.obj.id,
                "objekt_nazev": r.obj.name,
                "hrozba": f.threat_code,
                "hrozba_nazev": f.threat_label,
                "zjisteni": f.fact,
                "zdroj": f.source,
                "datum_zdroje": f.source_date or "",
                "poznamka": f.caveat,
                "pravdepodobnost_uroven": f.probability_level if f.probability_level is not None else -1,
                "pravdepodobnost_text": f.probability_label or "",
                "hranicni_pripad": f.is_borderline,
                "nelze_urcit": f.data_unavailable,
                "geometry": Point(r.obj.lon, r.obj.lat),
            })
    if finding_rows:
        gpd.GeoDataFrame(finding_rows, crs="EPSG:4326").to_file(out_path, layer="vysledky", driver="GPKG")

    # Podkladové vrstvy (skutečná data stažená ze zdrojů - pro dohledatelnost)
    for layer_name, features in raw_layers.items():
        if not features:
            continue
        rows = []
        for feat in features:
            props = dict(feat.get("properties", {}))
            props["geometry"] = shape(feat["geometry"])
            rows.append(props)
        gpd.GeoDataFrame(rows, crs="EPSG:4326").to_file(out_path, layer=f"podklad_{layer_name}", driver="GPKG")
