import numpy as np
import pytest

from engine.physics.baseline import HistoricalBaselineCalculator, InsufficientHistory
from tests.fixtures.fake_datasource import FakeDataSource, make_daily_scenes
from tests.fixtures.mock_scenes import MOCK_GEOMETRY


def test_insufficient_history_raises():
    # jen 5 scén, MIN_HISTORICAL_SCENES=20
    scenes = make_daily_scenes("2026-01-01", 5, lambda i: -15.0)
    source = FakeDataSource(scenes)
    calc = HistoricalBaselineCalculator(source, lookback_days=365)

    with pytest.raises(InsufficientHistory):
        import asyncio
        asyncio.run(calc.compute(MOCK_GEOMETRY, as_of_date="2026-08-30"))


def test_percentile_reference_matches_numpy():
    # 100 scén rovnoměrně rozložených -20..-5 dB
    values = list(np.linspace(-20.0, -5.0, 100))
    scenes = make_daily_scenes("2026-01-01", 100, lambda i: values[i])
    source = FakeDataSource(scenes)
    calc = HistoricalBaselineCalculator(source, lookback_days=1000, dry_percentile=5.0, wet_percentile=95.0)

    import asyncio
    ref = asyncio.run(calc.compute(MOCK_GEOMETRY, as_of_date="2027-06-01"))

    expected_dry = np.percentile(values, 5.0)
    expected_wet = np.percentile(values, 95.0)
    assert ref.dry_db == pytest.approx(expected_dry, abs=0.01)
    assert ref.wet_db == pytest.approx(expected_wet, abs=0.01)
    assert ref.scenes_used == 100


def test_lookback_window_excludes_old_scenes():
    # scény od 2020, lookback jen 30 dní od as_of_date v 2026 -> žádná v okně -> InsufficientHistory
    scenes = make_daily_scenes("2020-01-01", 50, lambda i: -15.0)
    source = FakeDataSource(scenes)
    calc = HistoricalBaselineCalculator(source, lookback_days=30)

    with pytest.raises(InsufficientHistory):
        import asyncio
        asyncio.run(calc.compute(MOCK_GEOMETRY, as_of_date="2026-08-30"))
