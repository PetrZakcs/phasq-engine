"""
Datové modely pro průjezdnost terénu. Stejný vzor jako engine/ki/models.py
- source/source_date/caveat povinné na úrovni LayerReading, žádná tichá
hodnota bez zdroje (zadání pravidlo 1).
"""

from dataclasses import dataclass, field


@dataclass
class TrafficabilityPolygon:
    """Jeden polygon (pole/území) - vstup od uživatele."""
    id: str
    name: str
    geometry: dict  # GeoJSON Polygon, EPSG:4326
    source_note: str = ""


@dataclass
class LayerReading:
    """Jedno čtení z jednoho vstupního zdroje (kap. 3 zadání)."""
    layer_name: str
    value: float | str | bool | None
    source: str
    source_date: str | None
    caveat: str
    data_unavailable: bool = False


@dataclass
class TrafficabilityFinding:
    """Výsledek pro jeden polygon - klasifikace + plné zdůvodnění."""
    polygon_id: str
    polygon_name: str
    classification: str  # "Vhodné" | "Riziko" | "Nevhodné" | "Nelze určit"
    decisive_rule: str  # která podmínka z classify.py rozhodla, lidsky čitelné
    confidence: str  # "nízká" | "střední" | "vysoká"
    confidence_reason: str
    sentinel1_scene_date: str | None
    sentinel1_age_days: int | None
    layers: list[LayerReading] = field(default_factory=list)
    caveat: str = ""
    generated_at: str = ""
