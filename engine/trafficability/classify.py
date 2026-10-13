"""
Klasifikace průjezdnosti terénu - čistá logika, ŽÁDNÉ I/O (stejný vzor
jako engine/ki/scale.py). Transparentní pravidla, ne AI - každé pravidlo
čitelné z výstupu (zadání kap. 4).

PRAVIDLO ZADÁNÍ: "Žádný vymyšlený práh. Pokud práh nejde doložit,
pravidlo nepoužívej a zapiš to do ADR." Viz docs/ADR-013-pruchodnost-klasifikace.md
pro úplné zdůvodnění a citace. Shrnutí tady v kódu:

- RELATIVE_MOISTURE_HIGH_PCT=90.0: konvergence literatury k 90-95 %
  field capacity jako kritériu "nesjízdno" (Ontario/Guelph historická
  kritéria 90-95 % FC, kalifornská HYDRUS-1D studie 85-95 % FC podle
  textury). relative_moisture_pct NENÍ doslova % field capacity (je to
  pozice mezi lokálním historickým suchým/5. percentil a mokrým/95.
  percentil SAR signálem) - použito jako ROZUMNÁ ANALOGIE (95. percentil
  historicky nejvlhčích podmínek ~ blízko přirozeného max. nasycení),
  NE jako fyzikálně identická veličina. Nižší konec citovaného rozsahu
  (85 %) explicitně PŘESKOČEN - zvolena konzervativnější (vyšší, tedy
  méně citlivá) hodnota 90, aby se chyba kalibrace nekompenzovala
  přehnaně citlivým prahem.
- PRECIP_72H_RISK_MM=5.0: jediná nalezená studie s konkrétní mm hodnotou
  (brazilská, denní srážky <5mm = příznivý den pro techniku, zde invertováno
  na kumulativní riziko za 72h). NÍZKÁ DŮVĚRYHODNOST - jedna studie, jiný
  klimatický region, denní ne kumulativní hodnota. Promítá se do
  confidence pole výstupu, ne do samotného prahu.
- CLAY_HIGH_PCT=40.0: USDA půdní texturní trojúhelník, hranice třídy
  "Clay" (jíl) - standardní taxonomická klasifikace (Soil Survey Manual),
  NE empiricky odvozený práh průjezdnosti specificky. Literatura
  o průjezdnosti dává jíl/jílovitost jako kvalitativní rizikový faktor
  (vertisoly, jílovité horizonty -> vyšší riziko kolejí), ale bez
  vlastního číselného prahu - proto použita nejbližší OBJEKTIVNÍ,
  doložitelná hranice (USDA klasifikace), ne vymyšlené číslo.
- SKLON (slope): NEPOUŽITO jako rozhodovací pravidlo. Hledání (NATO
  NRMM/AVT-308, zemědělská literatura, FAO/USDA land capability) nenašlo
  obecný, na konkrétním stroji nezávislý práh - jen specifikace
  konkrétních kombajnů (10-38 % podle modelu/výrobce), což není
  přenositelné na "obecnou třídu těžké zemědělské techniky" (zadání
  kap. 2). Sklon se PROTO POČÍTÁ a REPORTUJE (LayerReading), ale
  NEZVYŠUJE třídu rizika - odchylka od navržené struktury v zadání,
  zdůvodněná v ADR-013, ne přehlédnutá.

Hranice tříd WorldCover (v200, živě ověřeno ADR-012): 40=Cropland (orná
půda), 30=Grassland (louka). Vše ostatní (les, voda, zástavba, ...) mimo
rozsah v1.
"""

from dataclasses import dataclass, field

WORLDCOVER_CROPLAND = 40
WORLDCOVER_GRASSLAND = 30
IN_SCOPE_LAND_COVER_CLASSES = {WORLDCOVER_CROPLAND, WORLDCOVER_GRASSLAND}

RELATIVE_MOISTURE_HIGH_PCT = 90.0
PRECIP_72H_RISK_MM = 5.0
CLAY_HIGH_PCT = 40.0

CLASS_ORDER = ["Vhodné", "Riziko", "Nevhodné"]  # pro "zvýšit o jednu třídu" (pravidlo 6)


@dataclass
class ClassificationInput:
    land_cover_class: int | None  # ESA WorldCover kód, None = nelze určit
    reference_source: str | None  # "local_baseline" | "global_fallback" | None
    relative_moisture_pct: float | None
    precip_72h_mm: float | None
    precip_data_age_days: int | None  # skutečná latence použitých srážkových dat
    clay_pct: float | None
    sentinel1_scene_date: str | None
    sentinel1_age_days: int | None
    backscatter_jump_detected: bool = False  # STATUS #10 - skoková změna (orba/sklizeň)


@dataclass
class ClassificationResult:
    classification: str
    decisive_rule: str
    confidence: str
    confidence_reason: str
    caveats: list[str] = field(default_factory=list)


def _bump_one_class(classification: str) -> str:
    """Zvýší třídu rizika o jednu (pravidlo 6) - nikdy nesnižuje, nikdy
    nepřeskočí přes 'Nevhodné'."""
    if classification not in CLASS_ORDER:
        return classification
    idx = CLASS_ORDER.index(classification)
    return CLASS_ORDER[min(idx + 1, len(CLASS_ORDER) - 1)]


def classify(inp: ClassificationInput) -> ClassificationResult:
    caveats: list[str] = []

    # Pravidlo 1: pokryv mimo ornou půdu/louku -> Nelze určit
    if inp.land_cover_class is None:
        return ClassificationResult(
            "Nelze určit", "Pravidlo 1: krajinný pokryv neznámý",
            "nízká", "Vrstva krajinného pokryvu nedostupná.",
        )
    if inp.land_cover_class not in IN_SCOPE_LAND_COVER_CLASSES:
        return ClassificationResult(
            "Nelze určit",
            f"Pravidlo 1: krajinný pokryv (kód {inp.land_cover_class}) není orná půda ani louka",
            "vysoká",
            "Mimo rozsah v1 (jen orná půda a trvalý travní porost).",
        )

    # Pravidlo 2 (ADR-008): global_fallback nedává verdikt
    if inp.reference_source != "local_baseline":
        return ClassificationResult(
            "Nelze určit", "Pravidlo 2 (ADR-008): reference_source != local_baseline",
            "nízká",
            "Chybí lokální historická reference pro tohle pole - stejné pravidlo "
            "jako u drought_severity v RadiometricAnalyzer (ADR-008), relativní "
            "vlhkost bez lokální kalibrace by dala nedůvěryhodný výsledek.",
        )

    if inp.relative_moisture_pct is None:
        return ClassificationResult(
            "Nelze určit", "Relativní vlhkost chybí navzdory local_baseline (neočekávané)",
            "nízká", "Vnitřní nekonzistence vstupu - relative_moisture_pct je None.",
        )

    high_moisture = inp.relative_moisture_pct >= RELATIVE_MOISTURE_HIGH_PCT
    high_precip = inp.precip_72h_mm is not None and inp.precip_72h_mm >= PRECIP_72H_RISK_MM

    if inp.precip_72h_mm is None:
        caveats.append("Srážková data za posledních 72h nejsou dostupná - pravidlo 3/4 vyhodnoceno jen podle vlhkosti.")
    elif inp.precip_data_age_days is not None and inp.precip_data_age_days > 3:
        caveats.append(
            f"Srážková data jsou {inp.precip_data_age_days} dní stará (NASA POWER latence) - "
            "'posledních 72h' je ve skutečnosti starší okno, ne aktuální stav."
        )

    if high_moisture and high_precip:
        classification = "Nevhodné"
        decisive_rule = (
            f"Pravidlo 3: relativní vlhkost {inp.relative_moisture_pct:.0f} % >= {RELATIVE_MOISTURE_HIGH_PCT:.0f} % "
            f"A srážky za 72h {inp.precip_72h_mm:.1f} mm >= {PRECIP_72H_RISK_MM:.0f} mm"
        )
    elif high_moisture or high_precip:
        classification = "Riziko"
        decisive_rule = (
            f"Pravidlo 4: relativní vlhkost {inp.relative_moisture_pct:.0f} % "
            f"{'>=' if high_moisture else '<'} {RELATIVE_MOISTURE_HIGH_PCT:.0f} %, "
            f"srážky za 72h {'>=' if high_precip else '<'} {PRECIP_72H_RISK_MM:.0f} mm "
            "(jedna z podmínek pravidla 3 splněna)"
        )
    else:
        classification = "Vhodné"
        decisive_rule = (
            f"Pravidlo 5: relativní vlhkost {inp.relative_moisture_pct:.0f} % < {RELATIVE_MOISTURE_HIGH_PCT:.0f} % "
            f"a srážky za 72h pod prahem"
        )

    # Pravidlo 6: textura (vysoký podíl jílu) zvyšuje o jednu třídu, nikdy nesnižuje.
    # Sklon záměrně NENÍ součástí - viz docstring modulu.
    if inp.clay_pct is not None and inp.clay_pct >= CLAY_HIGH_PCT:
        bumped = _bump_one_class(classification)
        if bumped != classification:
            decisive_rule += f" + Pravidlo 6: jíl {inp.clay_pct:.0f} % >= {CLAY_HIGH_PCT:.0f} % (USDA třída Clay) zvyšuje třídu"
            classification = bumped
    elif inp.clay_pct is None:
        caveats.append("Půdní textura (jíl) nedostupná - pravidlo 6 (zvýšení třídy) nemohlo být vyhodnoceno.")

    # Spolehlivost
    if inp.backscatter_jump_detected:
        confidence = "nízká"
        confidence_reason = (
            "Zjištěna skoková změna backscatteru mezi posledními scénami - "
            "typicky orba/sklizeň (STATUS #10), ne změna vlhkosti. Výsledek "
            "neopraven, jen označen jako méně spolehlivý."
        )
    elif inp.sentinel1_age_days is not None and inp.sentinel1_age_days > 6:
        confidence = "střední"
        confidence_reason = f"Poslední Sentinel-1 scéna je {inp.sentinel1_age_days} dní stará."
    elif inp.precip_72h_mm is not None and inp.precip_data_age_days and inp.precip_data_age_days > 3:
        confidence = "střední"
        confidence_reason = "Srážková data starší než deklarované 72h okno (NASA POWER latence)."
    elif inp.clay_pct is None:
        confidence = "střední"
        confidence_reason = "Textura půdy nedostupná, pravidlo 6 nevyhodnoceno."
    else:
        confidence = "vysoká"
        confidence_reason = "Lokální baseline, čerstvá Sentinel-1 scéna, všechny vrstvy dostupné."

    return ClassificationResult(classification, decisive_rule, confidence, confidence_reason, caveats)
