"""
PDF/GeoPackage/JSON výstup - stejný vzor jako engine/ki/{report,geopackage,
json_output}.py (zadání: "tenká vrstva nad vzory z engine/ki"). Datové typy
jsou jiné (TrafficabilityFinding má polygon, ne bod), takže se funkce
nesdílí přímo s engine/ki - fonty (DejaVu, ověřené pokrytí české
diakritiky) se ale fyzicky reused ze stejného adresáře, ne duplikovány.
"""

import json
from dataclasses import asdict
from pathlib import Path

import geopandas as gpd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from shapely.geometry import shape

from engine.trafficability.models import TrafficabilityFinding, TrafficabilityPolygon

_KI_FONTS_DIR = Path(__file__).parent.parent / "ki" / "fonts"
pdfmetrics.registerFont(TTFont("DejaVuSans", str(_KI_FONTS_DIR / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(_KI_FONTS_DIR / "DejaVuSans-Bold.ttf")))

DISCLAIMER = (
    "Průzkumný prototyp, NE produkt. Výstup NIKDY netvrdí 'projede' nebo "
    "'neprojede' jako fakt - je to odhad relativního rizika špatné "
    "průjezdnosti pro OBECNOU třídu těžké zemědělské techniky, s uvedenou "
    "spolehlivostí. Nerozlišuje typ vozidla, nepočítá cone index ani VCI. "
    "Validace viz docs/ADR-014-pruchodnost-validace.md."
)

CLASSIFICATION_COLORS = {
    "Vhodné": colors.HexColor("#d4edda"),
    "Riziko": colors.HexColor("#fff3cd"),
    "Nevhodné": colors.HexColor("#f8d7da"),
    "Nelze určit": colors.HexColor("#e2e3e5"),
}


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle(name="TTitle", parent=ss["Title"], fontSize=18, fontName="DejaVuSans-Bold"))
    ss.add(ParagraphStyle(name="TH2", parent=ss["Heading2"], spaceBefore=14, fontName="DejaVuSans-Bold"))
    ss.add(ParagraphStyle(name="TBody", parent=ss["BodyText"], spaceAfter=6, fontName="DejaVuSans"))
    ss.add(ParagraphStyle(name="TCaveat", parent=ss["BodyText"], textColor=colors.HexColor("#555555"), fontSize=8, fontName="DejaVuSans"))
    ss.add(ParagraphStyle(name="TDisclaimer", parent=ss["BodyText"], fontSize=8, textColor=colors.HexColor("#b30000"), fontName="DejaVuSans"))
    ss.add(ParagraphStyle(name="TLabel", parent=ss["BodyText"], fontName="DejaVuSans-Bold", fontSize=9, leading=11))
    return ss


def _label(text: str, styles) -> Paragraph:
    return Paragraph(text, styles["TLabel"])


def write_pdf(items: list[tuple[TrafficabilityPolygon, TrafficabilityFinding]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    doc = SimpleDocTemplate(str(out_path), pagesize=A4,
                             topMargin=20 * mm, bottomMargin=20 * mm,
                             leftMargin=20 * mm, rightMargin=20 * mm)
    story = [
        Paragraph("Průjezdnost terénu ze satelitních dat", styles["TTitle"]),
        Paragraph("Odhad rizika pro těžkou zemědělskou techniku (v1)", styles["TH2"]),
        Spacer(1, 6),
        Paragraph(DISCLAIMER, styles["TDisclaimer"]),
        Spacer(1, 10),
    ]

    for i, (poly, finding) in enumerate(items):
        if i > 0:
            story.append(PageBreak())
        story.append(Paragraph(poly.name, styles["TH2"]))
        story.append(Paragraph(f"Poloha: {poly.source_note}", styles["TBody"]))
        story.append(Paragraph(f"Vygenerováno: {finding.generated_at}", styles["TCaveat"]))
        story.append(Spacer(1, 8))

        class_row = Table(
            [[_label("Klasifikace", styles), finding.classification],
             [_label("Rozhodující pravidlo", styles), Paragraph(finding.decisive_rule, styles["TBody"])],
             [_label("Spolehlivost", styles), f"{finding.confidence} - {finding.confidence_reason}"],
             [_label("Scéna Sentinel-1", styles),
              f"{finding.sentinel1_scene_date or 'nedostupná'} ({finding.sentinel1_age_days if finding.sentinel1_age_days is not None else '?'} dní stará)"]],
            colWidths=[45 * mm, 125 * mm],
        )
        class_row.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "DejaVuSans"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eeeeee")),
            ("BACKGROUND", (1, 0), (1, 0), CLASSIFICATION_COLORS.get(finding.classification, colors.white)),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(class_row)
        story.append(Spacer(1, 10))

        if finding.caveat:
            story.append(Paragraph(f"<b>Co data neumí říct:</b> {finding.caveat}", styles["TCaveat"]))
            story.append(Spacer(1, 6))

        layer_rows = [[_label("Vrstva", styles), _label("Hodnota", styles), _label("Zdroj", styles)]]
        for layer in finding.layers:
            val = "Nelze určit" if layer.data_unavailable else str(layer.value)
            layer_rows.append([layer.layer_name, val, Paragraph(layer.source, styles["TCaveat"])])
        layer_table = Table(layer_rows, colWidths=[40 * mm, 30 * mm, 100 * mm])
        layer_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "DejaVuSans"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dddddd")),
        ]))
        story.append(layer_table)

    doc.build(story)


def write_geopackage(items: list[tuple[TrafficabilityPolygon, TrafficabilityFinding]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    poly_rows = [
        {"id": p.id, "name": p.name, "source_note": p.source_note, "geometry": shape(p.geometry)}
        for p, _ in items
    ]
    gpd.GeoDataFrame(poly_rows, crs="EPSG:4326").to_file(out_path, layer="polygony", driver="GPKG")

    result_rows = []
    for poly, finding in items:
        result_rows.append({
            "polygon_id": finding.polygon_id,
            "nazev": finding.polygon_name,
            "klasifikace": finding.classification,
            "rozhodujici_pravidlo": finding.decisive_rule,
            "spolehlivost": finding.confidence,
            "duvod_spolehlivosti": finding.confidence_reason,
            "s1_scena_datum": finding.sentinel1_scene_date or "",
            "s1_stari_dni": finding.sentinel1_age_days if finding.sentinel1_age_days is not None else -1,
            "poznamka": finding.caveat,
            "geometry": shape(poly.geometry),
        })
    gpd.GeoDataFrame(result_rows, crs="EPSG:4326").to_file(out_path, layer="vysledky", driver="GPKG")


def write_json(items: list[tuple[TrafficabilityPolygon, TrafficabilityFinding]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "polygony": [
            {
                "id": poly.id, "name": poly.name, "source_note": poly.source_note,
                "vysledek": asdict(finding),
            }
            for poly, finding in items
        ]
    }
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
