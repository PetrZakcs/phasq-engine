import asyncio

import numpy as np
import pytest

from engine.datasources.sentinel2_cdse import DENSE_VEGETATION_NDVI_THRESHOLD, NDVISample
from engine.physics.baseline import HistoricalBaselineCalculator, InsufficientHistory
from tests.fixtures.fake_datasource import FakeDataSource
from tests.fixtures.fake_ndvi_source import FakeNdviSource
from tests.fixtures.mock_scenes import MOCK_GEOMETRY, make_scene

AS_OF = "2026-08-30"


def _seasonal_scenes(years: list[int], values_per_year: int, mean_db_fn, day_offset: int = 0) -> list:
    """Scény ve stejném kalendářním okně (kolem 08-30 + day_offset) napříč danými roky."""
    from datetime import datetime, timedelta

    scenes = []
    center = datetime.strptime(AS_OF, "%Y-%m-%d")
    for year in years:
        year_center = center.replace(year=year) + timedelta(days=day_offset)
        for i in range(values_per_year):
            date = (year_center + timedelta(days=i - values_per_year // 2)).strftime("%Y-%m-%d")
            scenes.append(make_scene(date, mean_db_fn(year, i)))
    return scenes


def test_insufficient_history_raises():
    # 2 roky × 3 scény, MIN_SCENES_PER_YEAR=8 -> ani jeden rok se nekvalifikuje
    scenes = _seasonal_scenes([2024, 2025], 3, lambda y, i: -15.0)
    source = FakeDataSource(scenes)
    calc = HistoricalBaselineCalculator(source, lookback_years=5, seasonal_window_days=21)

    with pytest.raises(InsufficientHistory):
        asyncio.run(calc.compute(MOCK_GEOMETRY, as_of_date=AS_OF))


def test_median_of_per_year_percentiles_matches_manual_calc():
    """
    Referenci počítáme jako MEDIÁN z ROČNÍCH percentilů, ne percentil z
    jednoho poolu všech scén napříč lety (viz ADR-002 "NDVI hradlo padlo
    pod vlastní kontrolou" — pooled percentil je zranitelný vůči jednomu
    anomálnímu roku).
    """
    values = list(np.linspace(-20.0, -5.0, 60))
    years = [2021, 2022, 2023, 2024, 2025]

    def mean_db_fn(year, i):
        idx = (year - 2021) * 12 + i
        return values[idx % len(values)]

    scenes = _seasonal_scenes(years, 12, mean_db_fn)
    source = FakeDataSource(scenes)
    calc = HistoricalBaselineCalculator(source, lookback_years=5, seasonal_window_days=21, dry_percentile=5.0, wet_percentile=95.0)

    ref = asyncio.run(calc.compute(MOCK_GEOMETRY, as_of_date=AS_OF))

    per_year_dry = [np.percentile([mean_db_fn(y, i) for i in range(12)], 5.0) for y in years]
    per_year_wet = [np.percentile([mean_db_fn(y, i) for i in range(12)], 95.0) for y in years]
    assert ref.dry_db == pytest.approx(np.median(per_year_dry), abs=0.01)
    assert ref.wet_db == pytest.approx(np.median(per_year_wet), abs=0.01)
    assert ref.scenes_used == 60
    assert sorted(ref.years_used) == years


def test_one_anomalous_year_does_not_dominate_reference():
    """
    Regresní test na skutečný živý nález (ADR-002): jeden rok s extrémně
    vysokými hodnotami (drsnost povrchu / mokrá půda po žních, ne vegetace
    — NDVI hradlo tohle nezachytí) nesmí přetáhnout referenci, i když ten
    rok sám o sobě má víc scén než ostatní roky dohromady.
    """
    normal_years = _seasonal_scenes([2022, 2023, 2024, 2025], 10, lambda y, i: -12.0)
    # jeden anomální rok, 40 scén (víc než součet ostatních), extrémně vysoké hodnoty
    anomalous_year = _seasonal_scenes([2021], 40, lambda y, i: -4.0)

    source = FakeDataSource(normal_years + anomalous_year)
    calc = HistoricalBaselineCalculator(source, lookback_years=5, seasonal_window_days=21, dry_percentile=5.0, wet_percentile=95.0)

    ref = asyncio.run(calc.compute(MOCK_GEOMETRY, as_of_date=AS_OF))

    # Pooled percentil (starý způsob) by tady dal wet_db blízko -4.0 (40 z 80
    # scén je -4.0). Medián z 5 ročních percentilů dá medián(-12,-12,-12,-12,-4) = -12.0.
    assert ref.wet_db == pytest.approx(-12.0, abs=0.01)
    assert ref.dry_db == pytest.approx(-12.0, abs=0.01)


def test_never_includes_current_year():
    """
    Kritická vlastnost (viz baseline.py docstring, ADR-002): reference NESMÍ
    obsahovat aktuální rok, jinak by probíhající sucho zředilo vlastní
    referenci. Scéna v roce 2026 (aktuální rok AS_OF) s extrémní hodnotou
    (-50 dB) NESMÍ ovlivnit percentil, i když leží přesně v sezónním okně.
    """
    past_years_scenes = _seasonal_scenes([2022, 2023, 2024, 2025], 10, lambda y, i: -12.0)
    current_year_outlier = _seasonal_scenes([2026], 5, lambda y, i: -50.0)

    source = FakeDataSource(past_years_scenes + current_year_outlier)
    calc = HistoricalBaselineCalculator(source, lookback_years=5, seasonal_window_days=21)

    ref = asyncio.run(calc.compute(MOCK_GEOMETRY, as_of_date=AS_OF))

    assert ref.dry_db > -20.0  # kdyby se -50 dB dostalo do percentilu, dry_db by bylo mnohem nižší
    assert 2026 not in ref.years_used
    assert ref.scenes_used == 40  # jen 4 minulé roky × 10, ne +5 z aktuálního roku


def test_seasonal_window_excludes_out_of_season_scenes():
    """Scény mimo sezónní okno (jiná část roku) se nesmí počítat do reference."""
    in_season = _seasonal_scenes([2022, 2023, 2024, 2025, 2021], 8, lambda y, i: -12.0, day_offset=0)
    out_of_season = _seasonal_scenes([2022, 2023, 2024, 2025, 2021], 8, lambda y, i: -3.0, day_offset=150)  # jiné roční období

    source = FakeDataSource(in_season + out_of_season)
    calc = HistoricalBaselineCalculator(source, lookback_years=5, seasonal_window_days=21)

    ref = asyncio.run(calc.compute(MOCK_GEOMETRY, as_of_date=AS_OF))

    # kdyby se -3 dB (jiná sezóna) dostalo dovnitř, wet_db by bylo blízko -3, ne -12
    assert ref.wet_db < -5.0


def _scenes_and_ndvi_with_split_vegetation(years: list[int], per_year: int, bare_db: float, dense_db: float, dense_ndvi: float):
    """
    Polovina scén za rok má NDVI nad `dense_ndvi` (simuluje hustou vegetaci,
    mean_db=dense_db), polovina pod (bare_db). Vrací (scenes, ndvi_samples)
    se stejnými daty, aby je nearest_ndvi spároval 1:1.
    """
    scenes = _seasonal_scenes(
        years, per_year,
        lambda y, i: dense_db if i % 2 == 0 else bare_db,
    )
    ndvi_samples = [
        NDVISample(date=s.acquisition_date, mean_ndvi=(dense_ndvi + 0.1) if s.roi_stats.mean_db == dense_db else 0.20, valid_pixel_ratio=1.0)
        for s in scenes
    ]
    return scenes, ndvi_samples


def test_default_ndvi_threshold_unchanged_behavior():
    """
    Regresní pojistka na parametrizaci (ADR-011, 2026-10-13): volání BEZ
    dense_vegetation_ndvi_threshold se musí chovat přesně jako dřív -
    práh DENSE_VEGETATION_NDVI_THRESHOLD (0.35) vyřadí scény s NDVI nad
    ním.
    """
    scenes, ndvi_samples = _scenes_and_ndvi_with_split_vegetation(
        [2021, 2022, 2023, 2024, 2025], per_year=16,
        bare_db=-12.0, dense_db=-4.0, dense_ndvi=DENSE_VEGETATION_NDVI_THRESHOLD,
    )
    source = FakeDataSource(scenes)
    ndvi_source = FakeNdviSource(ndvi_samples)
    calc = HistoricalBaselineCalculator(source, ndvi_source=ndvi_source, lookback_years=5, seasonal_window_days=21)

    ref = asyncio.run(calc.compute(MOCK_GEOMETRY, as_of_date=AS_OF))

    # -4.0 dB scény (NDVI nad prahem) vyřazeny -> wet_db blízko -12.0, ne -4.0
    assert ref.wet_db < -8.0
    assert ref.dense_vegetation_scenes_excluded == 5 * 8  # polovina z 16/rok, 5 let
    assert ref.dense_vegetation_ndvi_threshold_used == DENSE_VEGETATION_NDVI_THRESHOLD


def test_higher_ndvi_threshold_keeps_dense_scenes_and_changes_reference():
    """
    Hlavní test parametrizace: vyšší práh (0.6) NEVYŘADÍ scény s NDVI
    0.45 (nad starým prahem 0.35, pod novým 0.6) - referenci to změří
    jinak, viditelně.
    """
    scenes, ndvi_samples = _scenes_and_ndvi_with_split_vegetation(
        [2021, 2022, 2023, 2024, 2025], per_year=16,
        bare_db=-12.0, dense_db=-4.0, dense_ndvi=DENSE_VEGETATION_NDVI_THRESHOLD,
    )
    source = FakeDataSource(scenes)
    ndvi_source = FakeNdviSource(ndvi_samples)
    calc = HistoricalBaselineCalculator(
        source, ndvi_source=ndvi_source, lookback_years=5, seasonal_window_days=21,
        dense_vegetation_ndvi_threshold=0.6,
    )

    ref = asyncio.run(calc.compute(MOCK_GEOMETRY, as_of_date=AS_OF))

    # S prahem 0.6 (NDVI vzorky jsou 0.45) se nic nevyřadí -> wet_db tažené
    # vzhůru k -4.0 (95. percentil z poloviny scén na -4.0).
    assert ref.dense_vegetation_scenes_excluded == 0
    assert ref.wet_db > -8.0
    assert ref.dense_vegetation_ndvi_threshold_used == 0.6


def test_threshold_used_is_none_without_ndvi_source():
    """Bez ndvi_source se dense_vegetation_ndvi_threshold_used nehlásí jako
    použitý - hradlo vůbec neběželo, žádný práh se neaplikoval."""
    scenes = _seasonal_scenes([2021, 2022, 2023, 2024, 2025], 10, lambda y, i: -12.0)
    source = FakeDataSource(scenes)
    calc = HistoricalBaselineCalculator(source, lookback_years=5, seasonal_window_days=21)

    ref = asyncio.run(calc.compute(MOCK_GEOMETRY, as_of_date=AS_OF))

    assert ref.dense_vegetation_ndvi_threshold_used is None
    assert ref.ndvi_gated is False
