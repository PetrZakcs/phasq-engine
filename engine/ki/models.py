"""
Datové modely pro mapový podklad přírodních rizik KI.
Viz zadání (docs/ADR-009-ki-datove-zdroje.md pro zdroje, ADR-010 pro
architekturu Fáze 1).
"""

from dataclasses import dataclass, field


@dataclass
class KiObject:
    """Jeden objekt kritické infrastruktury - vstup od uživatele."""
    id: str
    name: str
    lon: float
    lat: float
    source_note: str = ""  # odkud se poloha vzala, pro ukázky (zadání pravidlo 4)


@dataclass
class ThreatFinding:
    """
    Jedno zjištění pro jednu hrozbu u jednoho objektu. Pravidlo 1 ze
    zadání (žádné vymyšlené číslo): source a source_date jsou povinné
    pro cokoliv, co není explicitně "nelze určit".
    """
    threat_code: str  # "povodne_navrhove" | "svahove_nestability" | "poddolovani" | "pohyby_terenu"
    threat_label: str  # lidsky čitelný název pro report
    fact: str  # "Objekt leží v záplavovém území Q20."
    source: str  # "VÚV TGM, ISVS Voda (ZaplavUzemi_Q20)"
    source_date: str | None  # datum poslední aktualizace zdroje, None jen když zdroj datum neudává
    caveat: str  # co data neumí říct - POVINNÉ pole, i když prázdný string by bylo podezřelé
    probability_level: int | None = None  # 1-5, None = "nenavrhuj" (zadání kap. 4)
    probability_label: str | None = None
    is_borderline: bool = False
    borderline_alternative_level: int | None = None
    borderline_alternative_label: str | None = None
    rationale: str = ""
    data_unavailable: bool = False  # True = "nelze určit", fact/caveat vysvětlí proč


@dataclass
class ObjectReport:
    obj: KiObject
    findings: list[ThreatFinding] = field(default_factory=list)
    generated_at: str = ""
