import pytest

from engine.physics.root_zone import compute_swi


def test_first_value_passes_through_unchanged():
    # K_1 = 1 v definici filtru — první pozorování se nemá co filtrovat.
    dates = ["2026-01-01", "2026-01-10"]
    ssm = [42.0, 50.0]
    swi = compute_swi(dates, ssm)
    assert swi[0] == pytest.approx(42.0)


def test_constant_series_is_steady_state():
    # Konstantní vstup nemá co vyhlazovat — SWI musí konvergovat k téže hodnotě.
    dates = [f"2026-01-{d:02d}" for d in range(1, 20, 2)]
    ssm = [55.0] * len(dates)
    swi = compute_swi(dates, ssm)
    for v in swi:
        assert v == pytest.approx(55.0, abs=1e-6)


def test_single_spike_is_damped_relative_to_raw_signal():
    # Toto je celý smysl SWI: jednorázový výkyv povrchové vlhkosti (déšť,
    # radarový artefakt) se nesmí projevit v odhadu kořenové zóny stejně
    # silně jako v syrovém povrchovém signálu.
    dates = ["2026-06-01", "2026-06-05", "2026-06-10", "2026-06-15", "2026-06-20"]
    ssm = [30.0, 30.0, 90.0, 30.0, 30.0]  # jediný výkyv uprostřed
    swi = compute_swi(dates, ssm)

    spike_index = 2
    raw_spike_deviation = abs(ssm[spike_index] - 30.0)
    swi_spike_deviation = abs(swi[spike_index] - 30.0)
    assert swi_spike_deviation < raw_spike_deviation


def test_larger_t_damps_more_than_smaller_t():
    # Větší T = "hlubší" integrace = silnější vyhlazení stejného vstupu.
    dates = ["2026-06-01", "2026-06-05", "2026-06-10"]
    ssm = [30.0, 30.0, 90.0]

    swi_shallow = compute_swi(dates, ssm, t_days=5.0)
    swi_deep = compute_swi(dates, ssm, t_days=60.0)

    assert abs(swi_deep[-1] - 30.0) < abs(swi_shallow[-1] - 30.0)


def test_output_length_matches_input():
    dates = ["2026-01-01", "2026-01-05", "2026-01-12"]
    ssm = [40.0, 45.0, 41.0]
    swi = compute_swi(dates, ssm)
    assert len(swi) == len(dates)


def test_single_point_returns_unchanged():
    swi = compute_swi(["2026-01-01"], [42.0])
    assert swi == [42.0]


def test_mismatched_lengths_raise():
    with pytest.raises(ValueError):
        compute_swi(["2026-01-01", "2026-01-02"], [1.0])
