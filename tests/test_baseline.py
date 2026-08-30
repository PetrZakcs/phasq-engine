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
