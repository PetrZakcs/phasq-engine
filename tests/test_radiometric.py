import pytest

from engine.physics.radiometric import (
    RadiometricAnalyzer,
    mean_backscatter_db,
    db_to_linear,
    linear_to_db,
)
from engine.physics.baseline import LocalReference
from engine.datasources.nasa_power_rootzone import RootZoneReading
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

    local_ref = LocalReference(dry_db=-13.72, wet_db=-8.66, scenes_used=188, years_used=[2021, 2022, 2023, 2024, 2025], seasonal_window_days=21)
    result_local = analyzer.analyze(scenes, MOCK_GEOMETRY, local_reference=local_ref)
    assert result_local["reference_source"] == "local_baseline"
    assert result_local["drought_risk"] is True
    assert result_local["reference_scenes_used"] == 188

    # stejný vstupní signál, různý verdikt podle reference - to je celý smysl ADR-002
    assert result_global["relative_moisture_pct"] > result_local["relative_moisture_pct"]


def test_measurement_caveat_present_in_output():
    result = RadiometricAnalyzer().analyze([make_wet_scene()], MOCK_GEOMETRY)
    assert "0-5 cm" in result["measurement_caveat"]


def test_root_zone_swi_damps_single_spike_more_than_surface_moisture():
    """
    Kořenová zóna (engine/physics/root_zone.py) musí na úrovni celého
    RadiometricAnalyzer výstupu skutečně tlumit jednorázový výkyv víc než
    syrová relative_moisture_pct - to je přesně ten typ šumu, co ADR-002
    zdokumentovalo jako otevřený problém (skok 19,3 % -> 61,5 % za 15 dní).
    """
    scenes = [
        make_scene("2026-06-01", -14.0),
        make_scene("2026-06-05", -14.0),
        make_scene("2026-06-10", -6.0),  # jednorázový výkyv (déšť/artefakt)
        make_scene("2026-06-15", -14.0),
        make_scene("2026-06-20", -14.0),
    ]
    result = RadiometricAnalyzer().analyze(scenes, MOCK_GEOMETRY)

    spike_entry = result["timeseries"][2]
    baseline_pct = result["timeseries"][0]["root_zone_swi_pct"]

    surface_deviation = abs(spike_entry["vv_db"] - (-14.0))  # jen orientačně, jiná škála
    swi_deviation_from_baseline = abs(spike_entry["root_zone_swi_pct"] - baseline_pct)

    # SWI v okamžiku výkyvu se musí od klidové hodnoty odchýlit MÉNĚ než
    # o celý rozsah global fallback škály (-22/-8 dB -> 0-100 %) by odpovídalo
    # syrové vlhkosti ve stejném bodě.
    spike_surface_pct = RadiometricAnalyzer()._sigma_to_moisture_pct(-6.0, -22.0, -8.0)
    baseline_surface_pct = RadiometricAnalyzer()._sigma_to_moisture_pct(-14.0, -22.0, -8.0)
    surface_swing = abs(spike_surface_pct - baseline_surface_pct)

    assert swi_deviation_from_baseline < surface_swing
    assert result["root_zone_swi_t_days"] == 20.0


def test_power_reading_kept_separate_from_sar_fields():
    """
    Regresní test na živý nález 2026-09-09 (ADR-003, ADR-006): SAR-only
    signál (relative_moisture_pct, root_zone_swi_pct) podhodnotil sucho
    i po lokální kalibraci ('mild' místo Intersucho 'extrémní').
    power_reading (NASA POWER) je nezávislý druhý zdroj - musí se
    objevit jako VLASTNÍ pole, ne přepsat/zprůměrovat SAR výstup.
    """
    scenes = [make_scene("2026-09-09", -10.24)]
    power = RootZoneReading(
        current_wetness=0.185,
        effective_date="2026-08-30",
        lag_days=10,
        percentile_rank=0.0,
        historical_min=0.245,
        historical_max=0.404,
        historical_samples=215,
        below_historical_range=True,
    )

    result_without_power = RadiometricAnalyzer().analyze(scenes, MOCK_GEOMETRY)
    result_with_power = RadiometricAnalyzer().analyze(scenes, MOCK_GEOMETRY, power_reading=power)

    assert result_without_power["power_root_zone_wetness"] is None
    assert result_with_power["power_root_zone_wetness"] == pytest.approx(0.185)
    assert result_with_power["power_root_zone_below_historical_range"] is True
    assert result_with_power["power_root_zone_percentile_rank"] == pytest.approx(0.0)
    assert result_with_power["power_root_zone_lag_days"] == 10

    # NASA POWER přítomnost nesmí změnit SAR-odvozená pole - oddělené zdroje.
    assert result_with_power["relative_moisture_pct"] == result_without_power["relative_moisture_pct"]
    assert result_with_power["root_zone_swi_pct"] == result_without_power["root_zone_swi_pct"]

    assert "NEZÁVISLÝ" in result_with_power["measurement_caveat"]
    assert "10 dní staré" in result_with_power["measurement_caveat"]
