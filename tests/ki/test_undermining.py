import pytest

from engine.ki.datasources import undermining


def _polygon_feature(lon_center: float, lat_center: float, nazev="Testová lokalita", surovina="uhlí", rok=1990, offset=0.001) -> dict:
    return {
        "type": "Feature",
        "properties": {"nazev": nazev, "surovina": surovina, "rok": rok},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [lon_center - offset, lat_center - offset],
                [lon_center + offset, lat_center - offset],
                [lon_center + offset, lat_center + offset],
                [lon_center - offset, lat_center + offset],
                [lon_center - offset, lat_center - offset],
            ]],
        },
    }


@pytest.mark.asyncio
async def test_no_features_in_range(mocker):
    mocker.patch("engine.ki.datasources.undermining.query_layer", return_value={"features": []})
    finding, raw = await undermining.get_undermining_finding(15.0, 49.0)

    assert finding.probability_level is None  # nenavrhuje se - zadání kap. 4
    assert "není" in finding.fact.lower() or "evidováno" in finding.fact.lower()


@pytest.mark.asyncio
async def test_object_inside_undermined_area_includes_year_as_source_date(mocker):
    feat = _polygon_feature(15.0, 49.0, nazev="Důl Jedna", surovina="černé uhlí", rok=1988, offset=0.01)
    mocker.patch("engine.ki.datasources.undermining.query_layer", return_value={"features": [feat]})
    finding, raw = await undermining.get_undermining_finding(15.0, 49.0)

    assert "leží v poddolovaném území" in finding.fact
    assert "Důl Jedna" in finding.fact
    assert finding.source_date == "1988"


@pytest.mark.asyncio
async def test_nearby_but_outside_reports_distance(mocker):
    feat = _polygon_feature(15.02, 49.02, offset=0.001)
    mocker.patch("engine.ki.datasources.undermining.query_layer", return_value={"features": [feat]})
    finding, raw = await undermining.get_undermining_finding(15.0, 49.0)

    assert "Nejbližší poddolované území je ve vzdálenosti" in finding.fact


@pytest.mark.asyncio
async def test_query_error_gives_data_unavailable(mocker):
    async def raise_error(*a, **k):
        raise undermining.ArcGisQueryError("boom")

    mocker.patch("engine.ki.datasources.undermining.query_layer", side_effect=raise_error)
    finding, raw = await undermining.get_undermining_finding(15.0, 49.0)

    assert finding.data_unavailable is True
