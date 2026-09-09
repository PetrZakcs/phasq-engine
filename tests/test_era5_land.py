from datetime import datetime, timedelta

import pytest

from engine.datasources.era5_land import Era5LandSource, Era5InsufficientHistory


def _make_raw(dates: list[str], values: list[float], depth_layer: str) -> dict:
    return {"daily": {"time": dates, depth_layer: values}}


def _daily_series(start: str, end: str, value_fn) -> tuple[list[str], list[float]]:
    """Vygeneruje denní řadu dat mezi start/end (včetně), hodnoty z value_fn(date)."""
    s = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end, "%Y-%m-%d")
    dates, values = [], []
    d = s
    while d <= e:
        ds = d.strftime("%Y-%m-%d")
        dates.append(ds)
        values.append(value_fn(d))
        d = d + timedelta(days=1)
    return dates, values


def test_below_historical_range_flagged():
    src = Era5LandSource(seasonal_window_days=5)
    layer = src.depth_layer

    # 5 historických let, konstantní vlhkost 0.30 v okně kolem 9/9 (2021-2025).
    # Dnešní (2026) hodnota je 0.10 - hluboko pod historickým minimem.
    dates, values = [], []
    for year in range(2021, 2026):
        d, v = _daily_series(f"{year}-09-04", f"{year}-09-14", lambda _d: 0.30)
        dates += d
        values += v
    d2026, v2026 = _daily_series("2026-09-04", "2026-09-09", lambda _d: 0.10)
    dates += d2026
    values += v2026

    raw = _make_raw(dates, values, layer)
    reading = src._compute_reading(raw, datetime(2026, 9, 9))

    assert reading.current_vwc == pytest.approx(0.10)
    assert reading.below_historical_range is True
    assert reading.percentile_rank == pytest.approx(0.0)
    assert reading.historical_samples >= 30


def test_normal_value_within_historical_range():
    src = Era5LandSource(seasonal_window_days=5)
    layer = src.depth_layer

    dates, values = [], []
    for year in range(2021, 2026):
        # historie kolísá mezi 0.2 a 0.4
        d, v = _daily_series(f"{year}-09-04", f"{year}-09-14", lambda dd, y=year: 0.2 + 0.02 * (dd.day % 5))
        dates += d
        values += v
    d2026, v2026 = _daily_series("2026-09-09", "2026-09-09", lambda _d: 0.30)
    dates += d2026
    values += v2026

    raw = _make_raw(dates, values, layer)
    reading = src._compute_reading(raw, datetime(2026, 9, 9))

    assert reading.below_historical_range is False
    assert 0 <= reading.percentile_rank <= 100


def test_current_year_never_used_as_history():
    src = Era5LandSource(seasonal_window_days=5)
    layer = src.depth_layer

    # Jediná historie je z roku 2026 samotného (aktuální rok) - musí to
    # selhat na InsufficientHistory, ne použít aktuální rok jako referenci.
    dates, values = _daily_series("2026-09-04", "2026-09-14", lambda _d: 0.25)
    raw = _make_raw(dates, values, layer)

    with pytest.raises(Era5InsufficientHistory):
        src._compute_reading(raw, datetime(2026, 9, 9))


def test_missing_today_raises():
    src = Era5LandSource(seasonal_window_days=5)
    layer = src.depth_layer

    dates, values = [], []
    for year in range(2021, 2026):
        d, v = _daily_series(f"{year}-09-04", f"{year}-09-14", lambda _d: 0.30)
        dates += d
        values += v
    # žádná hodnota pro 2026-09-09 (reanalýza ještě nedoběhla)

    raw = _make_raw(dates, values, layer)
    with pytest.raises(Era5InsufficientHistory):
        src._compute_reading(raw, datetime(2026, 9, 9))


def test_insufficient_samples_raises():
    src = Era5LandSource(seasonal_window_days=5)
    layer = src.depth_layer

    # jen jeden historický rok - málo vzorků
    dates, values = _daily_series("2025-09-04", "2025-09-14", lambda _d: 0.30)
    d2026, v2026 = _daily_series("2026-09-09", "2026-09-09", lambda _d: 0.30)
    dates += d2026
    values += v2026

    raw = _make_raw(dates, values, layer)
    with pytest.raises(Era5InsufficientHistory):
        src._compute_reading(raw, datetime(2026, 9, 9))
