"""
PDF \"Mapový podklad přírodních rizik\" - jedna kapitola na objekt
(zadání kap. 2). Žádné shrnutí do jednoho čísla rizika - dopad (tabulka
č. 2) prototyp neurčuje (zadání kap. 2), jen pravděpodobnost a expozici.
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from engine.ki.models import ObjectReport

# Výchozí Helvetica v reportlab NEMÁ českou diakritiku (ř/ě/č/š/ž/ů...
# se vykreslí jako prázdný čtverec) - živě ověřeno při prvním běhu.
# DejaVu Sans má ověřené plné pokrytí (viz engine/ki/fonts/LICENSE,
# Bitstream Vera License, volně pro jakékoliv použití).
_FONTS_DIR = Path(__file__).parent / "fonts"
pdfmetrics.registerFont(TTFont("DejaVuSans", str(_FONTS_DIR / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(_FONTS_DIR / "DejaVuSans-Bold.ttf")))

DISCLAIMER = (
    "Tento dokument je podklad pro posouzení rizik dle vyhlášky č. 122/2026 "
    "Sb., NENÍ posouzením rizik samotným. Navržené úrovně pravděpodobnosti "
    "vyžadují potvrzení odpovědnou osobou subjektu kritické infrastruktury. "
    "Dopad (tabulka č. 2 vyhlášky) tento dokument neurčuje. "
    "PRŮZKUMNÝ PROTOTYP - NEPUBLIKOVAT, NESDÍLET MIMO JEDNÁNÍ S PROVOZOVATELEM "
    "UVEDENÉHO OBJEKTU."
)


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle(name="KiTitle", parent=ss["Title"], fontSize=18, fontName="DejaVuSans-Bold"))
    ss.add(ParagraphStyle(name="KiH2", parent=ss["Heading2"], spaceBefore=14, fontName="DejaVuSans-Bold"))
    ss.add(ParagraphStyle(name="KiBody", parent=ss["BodyText"], spaceAfter=6, fontName="DejaVuSans"))
    ss.add(ParagraphStyle(name="KiCaveat", parent=ss["BodyText"], textColor=colors.HexColor("#555555"), fontSize=8, fontName="DejaVuSans"))
    ss.add(ParagraphStyle(name="KiDisclaimer", parent=ss["BodyText"], fontSize=8, textColor=colors.HexColor("#b30000"), fontName="DejaVuSans"))
    ss.add(ParagraphStyle(name="KiLabel", parent=ss["BodyText"], fontName="DejaVuSans-Bold", fontSize=9, leading=11))
    return ss


def _label(text: str, styles) -> Paragraph:
    """Popisek v levém sloupci jako Paragraph, ne prostý string - dlouhé
    popisky (např. "Navržená pravděpodobnost") jinak přetékají přes
    hranici sloupce místo zalomení na další řádek."""
    return Paragraph(text, styles["KiLabel"])


def _finding_table(finding, styles) -> Table:
    rows = [
        [_label("Hrozba", styles), finding.threat_label],
        [_label("Zjištění", styles), Paragraph(finding.fact, styles["KiBody"])],
        [_label("Zdroj", styles), Paragraph(finding.source, styles["KiBody"])],
        [_label("Datum zdroje", styles), finding.source_date or "neuvedeno v API zdroje"],
    ]
    if not finding.data_unavailable:
        if finding.probability_level is not None:
            level_text = f"{finding.probability_level} - {finding.probability_label}"
            if finding.is_borderline:
                level_text += (
                    f" (HRANIČNÍ PŘÍPAD - alternativně "
                    f"{finding.borderline_alternative_level} - {finding.borderline_alternative_label})"
                )
            rows.append([_label("Navržená pravděpodobnost", styles), Paragraph(level_text, styles["KiBody"])])
            rows.append([_label("Zdůvodnění", styles), Paragraph(finding.rationale, styles["KiBody"])])
        else:
            rows.append([_label("Navržená pravděpodobnost", styles), "Nenavrhuje se (hrozba bez doby opakování)"])
    rows.append([_label("Co data neumí říct", styles), Paragraph(finding.caveat, styles["KiCaveat"])])

    t = Table(rows, colWidths=[40 * mm, 130 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "DejaVuSans"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eeeeee")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    if finding.data_unavailable:
        t.setStyle(TableStyle([("BACKGROUND", (1, 1), (1, 1), colors.HexColor("#fff3cd"))]))
    return t


def write_pdf(reports: list[ObjectReport], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    doc = SimpleDocTemplate(str(out_path), pagesize=A4,
                             topMargin=20 * mm, bottomMargin=20 * mm,
                             leftMargin=20 * mm, rightMargin=20 * mm)
    story = []

    story.append(Paragraph("Mapový podklad přírodních rizik", styles["KiTitle"]))
    story.append(Paragraph("Kritická infrastruktura - vyhláška č. 122/2026 Sb.", styles["KiH2"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(DISCLAIMER, styles["KiDisclaimer"]))
    story.append(Spacer(1, 10))

    for i, r in enumerate(reports):
        if i > 0:
            story.append(PageBreak())
        story.append(Paragraph(r.obj.name, styles["KiH2"]))
        story.append(Paragraph(
            f"Souřadnice: {r.obj.lat:.6f}, {r.obj.lon:.6f} (WGS84) &nbsp;|&nbsp; "
            f"Poloha: {r.obj.source_note}",
            styles["KiBody"],
        ))
        story.append(Paragraph(f"Vygenerováno: {r.generated_at}", styles["KiCaveat"]))
        story.append(Spacer(1, 8))

        for finding in r.findings:
            story.append(_finding_table(finding, styles))
            story.append(Spacer(1, 10))

    doc.build(story)
