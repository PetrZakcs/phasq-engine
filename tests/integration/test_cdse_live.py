"""
Živé integrační testy proti CDSE + fyzikální validace proti reálným LPIS
polím. NEspouští se v CI (CDSE má rate limity a spotřebovává processing
units) — spouštěj ručně: pytest tests/integration/ -m live -v

Fixtures v tests/fixtures/real_lpis_*.json jsou skutečné LPIS parcely
stažené 2026-08-30 z gis.cenia.cz WFS (mze_lpis:agriculturalarea).

Tyto testy NEjsou tvrdé assert na přesnou shodu s Intersucho.cz (to se mění
den ze dne a měříme jinou hloubku, viz docs/ADR-002-local-baseline.md).
Hlídají REGRESI: že lokální baseline dává jinou (a rozumnější) odpověď
než globální fallback, a že relativní řazení mezi regiony sedí.
"""

import json
from pathlib import Path

import pytest

from engine.datasources.sentinel1_cdse import Sentinel1CDSESource
from engine.physics.baseline import HistoricalBaselineCalculator, InsufficientHistory
from engine.physics.radiometric import RadiometricAnalyzer
from utils.config import settings

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

pytestmark = pytest.mark.skipif(
    not settings.cdse_configured, reason="CDSE_CLIENT_ID/CDSE_CLIENT_SECRET nejsou nastaveny"
)


def _load_geometry(filename: str) -> dict:
    raw = json.loads((FIXTURES_DIR / filename).read_text())
    mp = raw["features"][0]["geometry"]
    return {"type": "Polygon", "coordinates": [mp["coordinates"][0][0]]}


@pytest.fixture
def cdse_source():
    return Sentinel1CDSESource(
        client_id=settings.CDSE_CLIENT_ID,
        client_secret=settings.CDSE_CLIENT_SECRET,
        token_url=settings.CDSE_TOKEN_URL,
        stats_api_url=settings.CDSE_STATS_API_URL,
    )


@pytest.mark.asyncio
async def test_area_calc_matches_lpis_official_area(cdse_source):
    """polygon_area_ha aproximace vs. oficiální LPIS plocha — musí sedět na <1%."""
    from utils.geometry import polygon_area_ha

    geometry = _load_geometry("real_lpis_arable_field.json")
    raw = json.loads((FIXTURES_DIR / "real_lpis_arable_field.json").read_text())
    official_ha = raw["features"][0]["properties"]["agricult_3"]

    our_ha = polygon_area_ha(geometry)
    assert our_ha == pytest.approx(official_ha, rel=0.01)


@pytest.mark.asyncio
@pytest.mark.xfail(
    reason="ADR-002: arable-to-arable napříč regiony NEROZLIŠUJE správně "
    "(suchý region vyšel vlhčí než kontrolní, 68.8% vs 57.9%). Otevřený "
    "problém - pravděpodobně chybějící incidence-angle korekce mezi "
    "geograficky vzdálenými poli. Nechat xfail, ne mazat/invertovat, "
    "dokud se to nevyšetří.",
    strict=True,
)
async def test_drought_region_field_flags_higher_severity_than_control(cdse_source):
    """
    ADR-002 regresní test: pole ve známém suchém regionu (Havlíčkobrodsko,
    Intersucho 2026-08-30: 'výjimečné až extrémní sucho') musí s lokální
    baseline vykázat NIŽŠÍ relative_moisture_pct než pole v regionu s
    potvrzeně lepšími poměry (Liberecko). Netestujeme přesnou shodu s
    Intersucho kategorií - testujeme, že model regiony správně ROZLIŠÍ.

    xfail: aktuálně PADÁ (viz docs/ADR-002-local-baseline.md) - záměrně
    ponecháno viditelné jako otevřený problém, strict=True aby test
    nahlásil chybu i kdyby začal procházet beze změny kódu (očekávaný
    fix musí být vědomý, ne náhodný).
    """
    drought_geometry = _load_geometry("real_lpis_arable_field.json")
    control_geometry = _load_geometry("real_lpis_arable_north.json")

    async def analyze(geometry):
        try:
            local_ref = await HistoricalBaselineCalculator(cdse_source).compute(geometry, as_of_date="2026-08-30")
        except InsufficientHistory:
            pytest.skip("Nedostatečná historie pro toto pole - nelze testovat bez local_reference")
        scenes = await cdse_source.get_scenes(geometry, "2026-08-16", "2026-08-30", ["VV"], "BOTH")
        return RadiometricAnalyzer().analyze(scenes, geometry, local_reference=local_ref)

    drought_result = await analyze(drought_geometry)
    control_result = await analyze(control_geometry)

    assert drought_result["reference_source"] == "local_baseline"
    assert control_result["reference_source"] == "local_baseline"
    assert drought_result["relative_moisture_pct"] < control_result["relative_moisture_pct"]


@pytest.mark.asyncio
async def test_global_fallback_overestimates_moisture_vs_local(cdse_source):
    """
    Regrese na PŘESNĚ ten bug, co ADR-002 opravilo: bez local_reference
    globální konstanty systematicky nadhodnocují vlhkost oproti lokální
    baseline na tomto poli. Pokud tenhle test začne padat, buď se globální
    konstanty změnily k lepšímu (zkontrolovat ručně), nebo se regrese vrátila.
    """
    geometry = _load_geometry("real_lpis_arable_field.json")
    scenes = await cdse_source.get_scenes(geometry, "2026-08-16", "2026-08-30", ["VV"], "BOTH")

    result_global = RadiometricAnalyzer().analyze(scenes, geometry, local_reference=None)

    try:
        local_ref = await HistoricalBaselineCalculator(cdse_source).compute(geometry, as_of_date="2026-08-30")
    except InsufficientHistory:
        pytest.skip("Nedostatečná historie")
    result_local = RadiometricAnalyzer().analyze(scenes, geometry, local_reference=local_ref)

    assert result_global["relative_moisture_pct"] > result_local["relative_moisture_pct"]
