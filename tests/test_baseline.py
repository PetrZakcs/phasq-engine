import asyncio

import numpy as np
import pytest

from engine.physics.baseline import HistoricalBaselineCalculator, InsufficientHistory
from tests.fixtures.fake_datasource import FakeDataSource
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
    # jen 2 roky × 3 scény = 6, MIN_HISTORICAL_SCENES=20
    scenes = _seasonal_scenes([2024, 2025], 3, lambda y, i: -15.0)
    source = FakeDataSource(scenes)
    calc = HistoricalBaselineCalculator(source, lookback_years=5, seasonal_window_days=21)

    with pytest.raises(InsufficientHistory):
        asyncio.run(calc.compute(MOCK_GEOMETRY, as_of_date=AS_OF))


def test_percentile_reference_matches_numpy():
    values = list(np.linspace(-20.0, -5.0, 60))
    years = [2021, 2022, 2023, 2024, 2025]

    def mean_db_fn(year, i):
        idx = (year - 2021) * 12 + i
        return values[idx % len(values)]

    scenes = _seasonal_scenes(years, 12, mean_db_fn)
    source = FakeDataSource(scenes)
    calc = HistoricalBaselineCalculator(source, lookback_years=5, seasonal_window_days=21, dry_percentile=5.0, wet_percentile=95.0)

    ref = asyncio.run(calc.compute(MOCK_GEOMETRY, as_of_date=AS_OF))

    all_used = [mean_db_fn(y, i) for y in years for i in range(12)]
    assert ref.dry_db == pytest.approx(np.percentile(all_used, 5.0), abs=0.01)
    assert ref.wet_db == pytest.approx(np.percentile(all_used, 95.0), abs=0.01)
    assert ref.scenes_used == 60
    assert sorted(ref.years_used) == years


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
