import pytest

from engine.physics.agroclimate import (
    compute_gdd,
    find_last_spring_frost,
    find_first_autumn_frost,
    compute_precipitation_deficit_mm,
    historical_daily_precip_mean,
)


def test_gdd_known_values():
    # Den 1: (20+10)/2 - 5 = 10.  Den 2: (8+2)/2 - 5 = 0 (pod prahem, ořezáno na 0).
    # Den 3: (30+20)/2 - 5 = 20.
    tmax = [20.0, 8.0, 30.0]
    tmin = [10.0, 2.0, 20.0]
    assert compute_gdd(tmax, tmin, base_temp=5.0) == pytest.approx(30.0)


def test_gdd_never_negative_per_day():
    # I hluboko pod prahem se den nepočítá záporně, jen jako 0.
    tmax = [-5.0]
    tmin = [-15.0]
    assert compute_gdd(tmax, tmin, base_temp=5.0) == pytest.approx(0.0)


def test_gdd_mismatched_lengths_raise():
    with pytest.raises(ValueError):
        compute_gdd([1.0, 2.0], [1.0])


def test_last_spring_frost_finds_latest_before_cutoff():
    dates = ["2026-03-01", "2026-04-15", "2026-04-20", "2026-07-10"]
    tmin = [-2.0, -1.0, 3.0, -5.0]  # poslední mráz PŘED červencem je 4/15, ne 7/10
    result = find_last_spring_frost(dates, tmin, threshold=0.0, spring_cutoff_month=7)
    assert result == "2026-04-15"


def test_last_spring_frost_none_when_no_frost():
    dates = ["2026-04-01", "2026-04-02"]
    tmin = [5.0, 6.0]
    assert find_last_spring_frost(dates, tmin) is None


def test_first_autumn_frost_finds_earliest_after_start():
    dates = ["2026-07-01", "2026-09-05", "2026-09-20", "2026-10-01"]
    tmin = [-3.0, -1.0, -4.0, -6.0]  # první mráz OD srpna je 9/5, ne 7/1
    result = find_first_autumn_frost(dates, tmin, threshold=0.0, autumn_start_month=8)
    assert result == "2026-09-05"


def test_precipitation_deficit_negative_when_dry():
    current = [0.0, 0.0, 1.0]  # 1mm celkem za 3 dny
    historical_mean = 5.0  # 5mm/den normál -> 15mm očekáváno
    deficit = compute_precipitation_deficit_mm(current, historical_mean)
    assert deficit == pytest.approx(1.0 - 15.0)
    assert deficit < 0


def test_precipitation_surplus_when_wet():
    current = [10.0, 10.0]
    historical_mean = 2.0
    deficit = compute_precipitation_deficit_mm(current, historical_mean)
    assert deficit > 0


def test_historical_mean_excludes_current_year():
    dates = ["2024-06-01", "2025-06-01", "2026-06-01"]
    precip = [10.0, 20.0, 999.0]  # 999 je aktuální rok, nesmí zkreslit průměr
    mean = historical_daily_precip_mean(dates, precip, years_exclude={2026})
    assert mean == pytest.approx(15.0)  # (10+20)/2, ne (10+20+999)/3


def test_historical_mean_raises_when_all_excluded():
    dates = ["2026-06-01"]
    precip = [10.0]
    with pytest.raises(ValueError):
        historical_daily_precip_mean(dates, precip, years_exclude={2026})
