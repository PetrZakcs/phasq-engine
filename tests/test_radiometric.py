import pytest

from engine.physics.radiometric import (
    RadiometricAnalyzer,
    mean_backscatter_db,
    db_to_linear,
    linear_to_db,
)
from engine.physics.baseline import LocalReference
from tests.fixtures.mock_scenes import (
    MOCK_GEOMETRY,
    make_dry_scene,
    make_wet_scene,
    make_low_coverage_scene,
    make_scene,
)


def test_drought_detection_extreme():
    analyzer = RadiometricAnalyzer()
    result = analyzer.analyze([make_dry_scene()], MOCK_GEOMETRY)
    assert result["success"] is True
    assert result["drought_risk"] is True
    assert result["drought_severity"] == "extreme"
    assert result["mean_backscatter_vv_db"] < -17.0


def test_no_drought_wet_conditions():
    analyzer = RadiometricAnalyzer()
    result = analyzer.analyze([make_wet_scene()], MOCK_GEOMETRY)
    assert result["drought_risk"] is False
    assert result["relative_moisture_pct"] > 60


def test_negative_trend_soil_drying():
    analyzer = RadiometricAnalyzer()
    result = analyzer.analyze(
        [make_wet_scene("2026-04-01"), make_dry_scene("2026-07-15")], MOCK_GEOMETRY
    )
    assert result["trend_db"] < 0


def test_low_coverage_scene_is_dropped():
    analyzer = RadiometricAnalyzer()
    result = analyzer.analyze(
        [make_wet_scene("2026-04-01"), make_low_coverage_scene("2026-05-01")], MOCK_GEOMETRY
    )
    assert result["scenes_count"] == 1
    assert result["scenes_dropped_low_coverage"] == 1


def test_no_valid_scenes_returns_error():
    analyzer = RadiometricAnalyzer()
    result = analyzer.analyze([make_low_coverage_scene()], MOCK_GEOMETRY)
    assert result["success"] is False
    assert result["error_code"] == "no_scenes"


def test_mean_backscatter_db_averages_in_linear_scale():
    # Toto je regresní test na chybu #3 z master planu: mean([-10, -20]) dB
    # NESMÍ vyjít -15 dB (naivní aritmetický průměr). Musí se zprůměrovat
    # v lineárním výkonu a převést zpět.
    result = mean_backscatter_db([-10.0, -20.0])
    assert result != pytest.approx(-15.0, abs=0.01)
    naive_wrong_average = -15.0
    assert result > naive_wrong_average  # lineární průměr dvou hodnot je vždy >= naivní dB průměr


def test_db_linear_roundtrip():
    for db in [-30.0, -17.0, -5.0, 0.0]:
        assert linear_to_db(db_to_linear(db)) == pytest.approx(db, abs=1e-9)


def test_local_reference_changes_verdict_vs_global_fallback():
    """
    Regresní test na živě nalezený nález (ADR-002): reálné pole s
    mean_vv=-10.24 dB dostalo s globální referencí (-22/-8) "84% moisture,
    no drought" - v rozporu s nezávisle potvrzeným extrémním suchem. S
    lokální referencí pole (-13.72/-8.66) dostalo "68.8%, mild drought".
    Test hlídá, že se reference_source a verdikt SKUTEČNĚ liší podle toho,
    jestli je local_reference předaná - ne že se tiše ignoruje.
    """
    scenes = [make_scene("2026-08-30", -10.24)]
    analyzer = RadiometricAnalyzer()

    result_global = analyzer.analyze(scenes, MOCK_GEOMETRY, local_reference=None)
    assert result_global["reference_source"] == "global_fallback"
    assert result_global["drought_risk"] is False

    local_ref = LocalReference(dry_db=-13.72, wet_db=-8.66, scenes_used=188, lookback_days=365)
    result_local = analyzer.analyze(scenes, MOCK_GEOMETRY, local_reference=local_ref)
    assert result_local["reference_source"] == "local_baseline"
    assert result_local["drought_risk"] is True
    assert result_local["reference_scenes_used"] == 188

    # stejný vstupní signál, různý verdikt podle reference - to je celý smysl ADR-002
    assert result_global["relative_moisture_pct"] > result_local["relative_moisture_pct"]


def test_measurement_caveat_present_in_output():
    result = RadiometricAnalyzer().analyze([make_wet_scene()], MOCK_GEOMETRY)
    assert "0-5 cm" in result["measurement_caveat"]
