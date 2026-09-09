from datetime import datetime, timedelta

import pytest

from engine.datasources.nasa_power_rootzone import NasaPowerRootZoneSource, RootZoneInsufficientHistory


def _daily_series(start: str, end: str, value_fn) -> dict:
    s = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end, "%Y-%m-%d")
    out = {}
    d = s
    while d <= e:
        out[d.strftime("%Y%m%d")] = value_fn(d)
        d += timedelta(days=1)
    return out


def _make_raw(values: dict) -> dict:
    return {"properties": {"parameter": {"GWETROOT": values}}}


def test_effective_date_and_lag_reported_when_data_lags():
    src = NasaPowerRootZoneSource(seasonal_window_days=5)
    values = {}
    # Historie musí ležet kolem EFFECTIVE_DATE (8/30, kvůli lagu), ne kolem as_of_date (9/9).
    for year in range(2021, 2026):
        values.update(_daily_series(f"{year}-08-26", f"{year}-09-04", lambda _d: 0.55))
    # 2026: data jen do 8/30, as_of_date bude 9/9 -> lag 10 dní
    values.update(_daily_series("2026-08-26", "2026-08-30", lambda _d: 0.20))

    reading = src._compute_reading(_make_raw(values), datetime(2026, 9, 9))

    assert reading.effective_date == "2026-08-30"
    assert reading.lag_days == 10
    assert reading.current_wetness == pytest.approx(0.20)
    assert reading.below_historical_range is True


def test_fill_values_excluded():
    src = NasaPowerRootZoneSource(seasonal_window_days=5)
    values = {}
    for year in range(2021, 2026):
        values.update(_daily_series(f"{year}-08-24", f"{year}-09-03", lambda _d: 0.55))
    values["20260830"] = -999.0
    values["20260829"] = 0.30

    reading = src._compute_reading(_make_raw(values), datetime(2026, 9, 9))
    assert reading.effective_date == "2026-08-29"  # 8/30 je fill value, přeskočeno


def test_insufficient_history_raises():
    src = NasaPowerRootZoneSource(seasonal_window_days=5)
    values = _daily_series("2026-08-26", "2026-08-30", lambda _d: 0.30)  # jen aktuální rok
    with pytest.raises(RootZoneInsufficientHistory):
        src._compute_reading(_make_raw(values), datetime(2026, 9, 9))


def test_no_data_at_all_raises():
    src = NasaPowerRootZoneSource()
    with pytest.raises(RootZoneInsufficientHistory):
        src._compute_reading(_make_raw({}), datetime(2026, 9, 9))
