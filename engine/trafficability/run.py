"""
CLI pro průjezdnost terénu. Žádné UI, žádné API endpointy, žádná databáze
(zadání kap. 5) - jen soubory.

Použití: python -m engine.trafficability.run --input pole.geojson --date 2026-10-13 --out vystup/

Znovu používá existující engine moduly (Sentinel1CDSESource,
HistoricalBaselineCalculator, RadiometricAnalyzer, NasaPowerWeatherSource)
- neopisuje je, viz zadání pravidlo "existující moduly importuj, nekopíruj".
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from shapely.geometry import shape

from engine.datasources.nasa_power_weather import NasaPowerWeatherSource
from engine.datasources.sentinel1_cdse import Sentinel1CDSESource
from engine.datasources.sentinel2_cdse import Sentinel2NDVISource
from engine.physics.baseline import HistoricalBaselineCalculator, InsufficientHistory
from engine.physics.radiometric import RadiometricAnalyzer
from engine.trafficability.classify import ClassificationInput, classify
from engine.trafficability.datasources.dem import get_slope_reading
from engine.trafficability.datasources.era5_cds import get_volumetric_moisture_reading
from engine.trafficability.datasources.soilgrids import get_clay_reading
from engine.trafficability.datasources.worldcover import get_land_cover_reading
from engine.trafficability.models import LayerReading, TrafficabilityFinding, TrafficabilityPolygon
from engine.trafficability.outputs import write_geopackage, write_json, write_pdf
from utils.config import settings

# ADR-011: 0.5 místo systémového defaultu 0.35 - živě ověřeno, že opravuje
# local_baseline na orné půdě. Pro louku nepomáhá (viz ADR-011), honest
# Nelze určit přes ADR-008 pravidlo v classify.py.
NDVI_THRESHOLD_FOR_ARABLE = 0.5

SENTINEL1_LOOKBACK_DAYS = 14  # okno pro "aktuální" scény
PRECIP_LOOKBACK_DAYS = 10  # buffer nad NASA POWER latencí (živě ověřeno ~4 dny, ADR-012)
PRECIP_WINDOW_DAYS = 3  # "posledních 72h" ze zadání

# STATUS #10 / zadání kap. 7.2: skoková změna backscatteru (orba/sklizeň)
# detekována jako změna > polovina lokálního dry-wet rozpětí mezi dvěma
# posledními scénami - práh odvozený z POLE VLASTNÍ kalibrace (ADR-002
# princip "lokální, ne globální"), ne z externí literatury, protože tohle
# je datová kvalita, ne fyzikální práh.
JUMP_DETECTION_FRACTION_OF_RANGE = 0.5


def load_polygons(input_path: Path) -> list[TrafficabilityPolygon]:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    polygons = []
    for i, feat in enumerate(data["features"]):
        props = feat.get("properties", {})
        polygons.append(TrafficabilityPolygon(
            id=str(props.get("id", i)),
            name=props.get("name", f"Polygon {i}"),
            geometry=feat["geometry"],
            source_note=props.get("source_note", ""),
        ))
    return polygons


def _detect_backscatter_jump(timeseries: list[dict], dry_db: float | None, wet_db: float | None) -> bool:
    if len(timeseries) < 2 or dry_db is None or wet_db is None:
        return False
    last, prev = timeseries[-1]["vv_db"], timeseries[-2]["vv_db"]
    jump = abs(last - prev)
    local_range = abs(wet_db - dry_db)
    return local_range > 0 and jump > (JUMP_DETECTION_FRACTION_OF_RANGE * local_range)


async def process_polygon(poly: TrafficabilityPolygon, as_of_date: str) -> TrafficabilityFinding:
    centroid = shape(poly.geometry).centroid
    lon, lat = centroid.x, centroid.y
    as_of = datetime.strptime(as_of_date, "%Y-%m-%d")

    layers: list[LayerReading] = []

    land_cover = await get_land_cover_reading(lon, lat)
    layers.append(land_cover)

    slope = await get_slope_reading(lon, lat)
    layers.append(slope)

    clay = await get_clay_reading(lon, lat)
    layers.append(clay)

    era5 = await get_volumetric_moisture_reading(lon, lat)
    layers.append(era5)

    # Sentinel-1 + lokální baseline (ADR-011 threshold=0.5) - znovupoužito, neopsáno.
    relative_moisture_pct = None
    reference_source = None
    s1_scene_date = None
    s1_age_days = None
    jump_detected = False

    if not settings.cdse_configured:
        layers.append(LayerReading(
            "relativni_vlhkost", None, "Sentinel-1 CDSE", None,
            "Nelze určit - CDSE credentials nejsou nastaveny.", True,
        ))
    else:
        s1_source = Sentinel1CDSESource(
            client_id=settings.CDSE_CLIENT_ID, client_secret=settings.CDSE_CLIENT_SECRET,
            token_url=settings.CDSE_TOKEN_URL, stats_api_url=settings.CDSE_STATS_API_URL,
        )
        s2_source = Sentinel2NDVISource(
            client_id=settings.CDSE_CLIENT_ID, client_secret=settings.CDSE_CLIENT_SECRET,
            token_url=settings.CDSE_TOKEN_URL, stats_api_url=settings.CDSE_STATS_API_URL,
        )
        date_start = (as_of - timedelta(days=SENTINEL1_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

        try:
            scenes = await s1_source.get_scenes(poly.geometry, date_start, as_of_date, polarizations=["VV"])

            local_reference = None
            try:
                calc = HistoricalBaselineCalculator(
                    s1_source, ndvi_source=s2_source,
                    dense_vegetation_ndvi_threshold=NDVI_THRESHOLD_FOR_ARABLE,
                )
                local_reference = await calc.compute(poly.geometry, as_of_date=as_of_date)
            except InsufficientHistory:
                pass

            result = RadiometricAnalyzer().analyze(scenes, poly.geometry, local_reference=local_reference)

            if result.get("success"):
                relative_moisture_pct = result["relative_moisture_pct"]
                reference_source = result["reference_source"]
                timeseries = result["timeseries"]
                if timeseries:
                    s1_scene_date = timeseries[-1]["date"]
                    s1_age_days = (as_of - datetime.strptime(s1_scene_date, "%Y-%m-%d")).days
                jump_detected = _detect_backscatter_jump(
                    timeseries, result.get("reference_dry_db"), result.get("reference_wet_db"),
                )
                layers.append(LayerReading(
                    "relativni_vlhkost", round(relative_moisture_pct, 1),
                    f"Sentinel-1 CDSE + {reference_source}", s1_scene_date,
                    result.get("measurement_caveat", ""),
                ))
            else:
                layers.append(LayerReading(
                    "relativni_vlhkost", None, "Sentinel-1 CDSE", None,
                    f"Nelze určit - {result.get('error_message', 'analýza selhala')}.", True,
                ))
        except httpx.HTTPStatusError as e:
            layers.append(LayerReading(
                "relativni_vlhkost", None, "Sentinel-1 CDSE", None,
                f"Nelze určit - CDSE dotaz selhal ({e}).", True,
            ))

    # NASA POWER srážky - živě ověřená ~4denní latence (ADR-012), posledních 72h
    # reálně znamená "nejnovější dostupné 3denní okno", ne doslova teď.
    precip_72h_mm = None
    precip_data_age_days = None
    try:
        weather = NasaPowerWeatherSource()
        date_start = (as_of - timedelta(days=PRECIP_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
        daily = await weather.get_daily_weather(lat, lon, date_start, as_of_date)
        if daily.dates:
            last_n = daily.precipitation_mm[-PRECIP_WINDOW_DAYS:]
            precip_72h_mm = round(sum(last_n), 1)
            last_date = datetime.strptime(daily.dates[-1], "%Y-%m-%d")
            precip_data_age_days = (as_of - last_date).days
            layers.append(LayerReading(
                "srazky_72h_mm", precip_72h_mm, "NASA POWER (power.larc.nasa.gov)",
                daily.dates[-1],
                f"Součet posledních {PRECIP_WINDOW_DAYS} dostupných dní, {precip_data_age_days} dní staré "
                "(živě ověřená latence, ADR-012) - ne doslova posledních 72 hodin v reálném čase.",
            ))
        else:
            layers.append(LayerReading(
                "srazky_72h_mm", None, "NASA POWER", None, "Nelze určit - žádná dostupná data v okně.", True,
            ))
    except httpx.HTTPStatusError as e:
        layers.append(LayerReading(
            "srazky_72h_mm", None, "NASA POWER", None, f"Nelze určit - dotaz selhal ({e}).", True,
        ))

    classification_input = ClassificationInput(
        land_cover_class=land_cover.value if not land_cover.data_unavailable else None,
        reference_source=reference_source,
        relative_moisture_pct=relative_moisture_pct,
        precip_72h_mm=precip_72h_mm,
        precip_data_age_days=precip_data_age_days,
        clay_pct=clay.value if not clay.data_unavailable else None,
        sentinel1_scene_date=s1_scene_date,
        sentinel1_age_days=s1_age_days,
        backscatter_jump_detected=jump_detected,
    )
    result = classify(classification_input)

    caveat_text = " ".join(result.caveats) if result.caveats else ""

    return TrafficabilityFinding(
        polygon_id=poly.id,
        polygon_name=poly.name,
        classification=result.classification,
        decisive_rule=result.decisive_rule,
        confidence=result.confidence,
        confidence_reason=result.confidence_reason,
        sentinel1_scene_date=s1_scene_date,
        sentinel1_age_days=s1_age_days,
        layers=layers,
        caveat=caveat_text,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


async def run(input_path: Path, as_of_date: str, out_dir: Path) -> None:
    polygons = load_polygons(input_path)
    print(f"Načteno {len(polygons)} polygonů z {input_path}")

    items = []
    for poly in polygons:
        print(f"Zpracovávám: {poly.name}")
        finding = await process_polygon(poly, as_of_date)
        items.append((poly, finding))
        print(f"  -> {finding.classification} ({finding.decisive_rule})")

    out_dir.mkdir(parents=True, exist_ok=True)
    write_pdf(items, out_dir / "pruchodnost_terenu.pdf")
    write_geopackage(items, out_dir / "pruchodnost_terenu.gpkg")
    write_json(items, out_dir / "pruchodnost_terenu.json")
    print(f"Hotovo. Výstupy v {out_dir}/")


def main():
    parser = argparse.ArgumentParser(description="Průjezdnost terénu ze satelitních dat")
    parser.add_argument("--input", required=True, type=Path, help="GeoJSON s polygony")
    parser.add_argument("--date", required=True, help="Datum posouzení (YYYY-MM-DD)")
    parser.add_argument("--out", required=True, type=Path, help="Výstupní adresář")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Vstupní soubor neexistuje: {args.input}", file=sys.stderr)
        sys.exit(1)

    asyncio.run(run(args.input, args.date, args.out))


if __name__ == "__main__":
    main()
