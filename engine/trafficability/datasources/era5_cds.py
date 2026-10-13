"""
ERA5-Land (CDS) - objemová vlhkost 0-7cm.

NEDOKONČENO ZÁMĚRNĚ (stejný vzor jako engine/ki/datasources/egms.py):
živě ověřeno (ADR-012), že CDS (cds.climate.copernicus.eu) je SAMOSTATNÁ
platforma, ne CDSE - vyžaduje vlastní ECMWF účet a CDS_API_KEY. Navíc i
s tokenem: finální produkt je 2-3 měsíce starý, NRT varianta
(ERA5-Land-T) ~5 dní ale nekvalitně ověřená. Bez tokenu honest "Nelze
určit", ne fingovaná hodnota (zadání pravidlo 1).
"""

import os

from engine.trafficability.models import LayerReading

SOURCE_LABEL = "ERA5-Land (Climate Data Store, cds.climate.copernicus.eu)"


async def get_volumetric_moisture_reading(lon: float, lat: float) -> LayerReading:
    token = os.environ.get("CDS_API_KEY")

    if not token:
        return LayerReading(
            layer_name="objemova_vlhkost_0_7cm",
            value=None,
            source=SOURCE_LABEL,
            source_date=None,
            caveat=(
                "Chybí CDS_API_KEY. ERA5-Land vyžaduje samostatnou registraci "
                "na cds.climate.copernicus.eu (CDSE credentials nestačí) - viz "
                "docs/ADR-012-pruchodnost-datove-zdroje.md. I s tokenem: finální "
                "produkt je 2-3 měsíce starý, NRT varianta (ERA5-Land-T) ~5 dní "
                "ale nekvalitně ověřená - nikdy nebude opravdu 'aktuální stav'."
            ),
            data_unavailable=True,
        )

    # TODO: implementace po získání CDS_API_KEY - viz docstring výš.
    return LayerReading(
        layer_name="objemova_vlhkost_0_7cm",
        value=None,
        source=SOURCE_LABEL,
        source_date=None,
        caveat="CDS_API_KEY je nastaven, ale stahovací logika zatím není implementována.",
        data_unavailable=True,
    )
