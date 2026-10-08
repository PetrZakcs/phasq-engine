"""
EGMS (European Ground Motion Service) - pohyby terénu.

NEDOKONČENO ZÁMĚRNĚ: živě ověřeno (viz docs/ADR-009-ki-datove-zdroje.md),
že EGMS vyžaduje SAMOSTATNÝ CLMS API token (land.copernicus.eu), ne
CDSE credentials, co už appka má. Bez tokenu tenhle zdroj vrací
"nelze určit" - zadání pravidlo 1 (žádné vymyšlené číslo) platí i tady,
radši chybějící zdroj než fingovaný.

Oficiální distribuce: github.com/copernicus-land/egms-api (Jupyter/CSV
workflow) - ne přímý WFS/WMS jako u ostatních tří zdrojů. Implementace
skutečného stažení je otevřený bod pro další fázi, až bude token
k dispozici.
"""

import os

from engine.ki.models import ThreatFinding

SOURCE_LABEL = "Copernicus Land Monitoring Service, EGMS (egms.land.copernicus.eu)"


async def get_egms_finding(lon: float, lat: float) -> tuple[ThreatFinding, list[dict]]:
    token = os.environ.get("CLMS_API_TOKEN")

    if not token:
        finding = ThreatFinding(
            threat_code="pohyby_terenu",
            threat_label="Pohyby terénu (EGMS)",
            fact="Nelze určit.",
            source=SOURCE_LABEL,
            source_date=None,
            caveat=(
                "Chybí CLMS_API_TOKEN. EGMS vyžaduje samostatnou registraci "
                "na land.copernicus.eu (CDSE credentials nestačí) - viz "
                "docs/ADR-009-ki-datove-zdroje.md. Po získání tokenu "
                "doplnit skutečné stažení přes github.com/copernicus-land/egms-api."
            ),
            data_unavailable=True,
        )
        return finding, []

    # TODO: implementace po získání CLMS_API_TOKEN - viz docstring výš.
    finding = ThreatFinding(
        threat_code="pohyby_terenu",
        threat_label="Pohyby terénu (EGMS)",
        fact="Nelze určit.",
        source=SOURCE_LABEL,
        source_date=None,
        caveat="CLMS_API_TOKEN je nastaven, ale stahovací logika zatím není implementována.",
        data_unavailable=True,
    )
    return finding, []
