"""
CLI pro mapový podklad přírodních rizik KI.

Použití: python -m engine.ki.run --input objekty.geojson --out vystup/

Vstupní GeoJSON: FeatureCollection bodů, properties.name = název objektu
(properties.id volitelné, jinak se odvodí z pořadí).

Žádné UI, žádné API endpointy, žádná databáze - jen soubory (zadání kap. 5).
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from engine.ki.datasources.egms import get_egms_finding
from engine.ki.datasources.flood_zones import get_flood_finding
from engine.ki.datasources.landslides import get_landslide_finding
from engine.ki.datasources.undermining import get_undermining_finding
from engine.ki.geopackage import write_geopackage
from engine.ki.json_output import write_json
from engine.ki.models import KiObject, ObjectReport
from engine.ki.report import write_pdf


def load_objects(input_path: Path) -> list[KiObject]:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    objects = []
    for i, feat in enumerate(data["features"]):
        props = feat.get("properties", {})
        lon, lat = feat["geometry"]["coordinates"][:2]
        objects.append(KiObject(
            id=str(props.get("id", i)),
            name=props.get("name", f"Objekt {i}"),
            lon=lon,
            lat=lat,
            source_note=props.get("source_note", ""),
        ))
    return objects


async def process_object(obj: KiObject) -> tuple[ObjectReport, dict]:
    flood_finding, flood_raw = await get_flood_finding(obj.lon, obj.lat)
    landslide_finding, landslide_raw = await get_landslide_finding(obj.lon, obj.lat)
    undermining_finding, undermining_raw = await get_undermining_finding(obj.lon, obj.lat)
    egms_finding, egms_raw = await get_egms_finding(obj.lon, obj.lat)

    report = ObjectReport(
        obj=obj,
        findings=[flood_finding, landslide_finding, undermining_finding, egms_finding],
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    raw = {
        "zaplavova_uzemi": flood_raw,
        "svahove_nestability": landslide_raw,
        "poddolovani": undermining_raw,
    }
    return report, raw


async def run(input_path: Path, out_dir: Path) -> None:
    objects = load_objects(input_path)
    print(f"Načteno {len(objects)} objektů z {input_path}")

    reports: list[ObjectReport] = []
    all_raw: dict[str, list] = {"zaplavova_uzemi": [], "svahove_nestability": [], "poddolovani": []}

    for obj in objects:
        print(f"Zpracovávám: {obj.name} ({obj.lon}, {obj.lat})")
        report, raw = await process_object(obj)
        reports.append(report)
        for key, features in raw.items():
            all_raw[key].extend(features)

    out_dir.mkdir(parents=True, exist_ok=True)
    write_pdf(reports, out_dir / "mapovy_podklad_prirodnich_rizik.pdf")
    write_geopackage(reports, all_raw, out_dir / "mapovy_podklad_prirodnich_rizik.gpkg")
    write_json(reports, out_dir / "mapovy_podklad_prirodnich_rizik.json")

    print(f"Hotovo. Výstupy v {out_dir}/")


def main():
    parser = argparse.ArgumentParser(description="Mapový podklad přírodních rizik KI")
    parser.add_argument("--input", required=True, type=Path, help="GeoJSON s objekty (body)")
    parser.add_argument("--out", required=True, type=Path, help="Výstupní adresář")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Vstupní soubor neexistuje: {args.input}", file=sys.stderr)
        sys.exit(1)

    asyncio.run(run(args.input, args.out))


if __name__ == "__main__":
    main()
