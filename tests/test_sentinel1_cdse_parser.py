"""
Regresní testy na ADR-007 (nález z externí review, 2026-10-01) - chyběly
dřív, přestože obě opravy byly živě ověřené. Bez nich by se dalo kdykoliv
omylem vrátit k dB-před-agregací nebo špatnému valid_pixel_ratio vzorci
beze změny v žádném testu.
"""

from engine.datasources.sentinel1_cdse import Sentinel1CDSESource
from utils.decibel import linear_to_db
from tests.fixtures.mock_scenes import MOCK_GEOMETRY


def _make_source() -> Sentinel1CDSESource:
    return Sentinel1CDSESource(
        client_id="test", client_secret="test",
        token_url="https://example.invalid/token",
        stats_api_url="https://example.invalid/statistics",
    )


def _raw_response(geometry_pixel_count, sample_count, no_data_count, mean_linear, stdev_linear=0.0, p10_linear=None, p90_linear=None):
    return {
        "geometryPixelCount": geometry_pixel_count,
        "data": [
            {
                "interval": {"from": "2026-07-01T00:00:00Z", "to": "2026-07-02T00:00:00Z"},
                "outputs": {
                    "default": {
                        "bands": {
                            "B0": {
                                "stats": {
                                    "sampleCount": sample_count,
                                    "noDataCount": no_data_count,
                                    "mean": mean_linear,
                                    "stDev": stdev_linear,
                                    "percentiles": {
                                        "10.0": p10_linear if p10_linear is not None else mean_linear,
                                        "90.0": p90_linear if p90_linear is not None else mean_linear,
                                    },
                                }
                            }
                        }
                    }
                },
            }
        ],
    }


def test_mean_db_matches_linear_to_db_of_server_mean():
    # ADR-007 oprava 1: server agreguje LINEÁRNĚ (mean_linear v odpovědi),
    # dB převod je až tady. Živě ověřený rozdíl proti opačnému postupu
    # (dB per-pixel, server zprůměruje dB) byl 0,624 dB pro reálnou scénu.
    source = _make_source()
    mean_linear = 0.025
    raw = _raw_response(geometry_pixel_count=100, sample_count=100, no_data_count=0, mean_linear=mean_linear)

    scenes = source._parse_stats_response(raw, MOCK_GEOMETRY, "VV")

    expected_db = linear_to_db(mean_linear)
    assert abs(scenes[0].roi_stats.mean_db - expected_db) < 1e-9

    # Regresní pojistka na chybu, co ADR-007 opravilo: naivní (a ŠPATNÝ)
    # postup by počítal dB z nějaké jiné, dB-průměrované hodnoty - dokud
    # evalscript/parsing pracuje v lineární škále až do tohoto bodu, musí
    # se mean_db rovnat PŘESNĚ linear_to_db(mean_linear), ne přibližně
    # nějaké jiné hodnotě o ~0.6 dB vedle.
    wrong_naive_db = linear_to_db(mean_linear) + 0.624
    assert abs(scenes[0].roi_stats.mean_db - wrong_naive_db) > 0.5


def test_valid_pixel_ratio_uses_geometry_pixel_count_not_sample_count():
    # ADR-007 oprava 2: (sampleCount - noDataCount) / geometryPixelCount,
    # NE / sampleCount (to by pro nepravidelné pole měřilo hlavně tvar
    # pole vůči jeho obdélníkovému obalu).
    source = _make_source()
    raw = _raw_response(
        geometry_pixel_count=120,  # skutečný počet pixelů POD polygonem
        sample_count=150,  # pixely v BOUNDING BOXU (víc, obalový obdélník)
        no_data_count=50,
        mean_linear=0.02,
    )

    scenes = source._parse_stats_response(raw, MOCK_GEOMETRY, "VV")

    valid_in_polygon = 150 - 50  # 100
    expected_ratio = valid_in_polygon / 120  # 0.8333..., NE 100/150=0.667
    assert abs(scenes[0].roi_stats.valid_pixel_ratio - expected_ratio) < 1e-9

    wrong_ratio_using_sample_count = valid_in_polygon / 150
    assert abs(scenes[0].roi_stats.valid_pixel_ratio - wrong_ratio_using_sample_count) > 0.1


def test_valid_pixel_ratio_falls_back_when_geometry_pixel_count_missing():
    source = _make_source()
    raw = _raw_response(geometry_pixel_count=None, sample_count=100, no_data_count=20, mean_linear=0.02)

    scenes = source._parse_stats_response(raw, MOCK_GEOMETRY, "VV")

    # Fallback: konzervativní odhad (sampleCount - noDataCount) / sampleCount,
    # ne pád na chybě, když neočekávaně chybí top-level pole.
    assert abs(scenes[0].roi_stats.valid_pixel_ratio - 0.8) < 1e-9


def test_zero_sample_count_interval_is_skipped():
    source = _make_source()
    raw = _raw_response(geometry_pixel_count=100, sample_count=0, no_data_count=0, mean_linear=0.02)

    scenes = source._parse_stats_response(raw, MOCK_GEOMETRY, "VV")

    assert scenes == []
