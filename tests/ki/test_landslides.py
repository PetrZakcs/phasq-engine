import pytest

from engine.ki.datasources import landslides


def _polygon_feature(lon_center: float, lat_center: float, aktivita=1, nazev=1000, offset=0.001) -> dict:
    return {
        "type": "Feature",
        "properties": {"aktivita": aktivita, "nazev": nazev},
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
    mocker.patch("engine.ki.datasources.landslides.query_layer", return_value={"features": []})
    finding, raw = await landslides.get_landslide_finding(15.0, 49.0)

    assert finding.probability_level is None  # nenavrhuje se - zadání kap. 4
    assert "není" in finding.fact.lower()
    assert raw == []


@pytest.mark.asyncio
async def test_nearby_deformation_reports_distance_and_decoded_labels(mocker):
    # polygon ~0.001 deg posunutý - objekt je mimo polygon, test ověřuje
    # nenulovou vzdálenost + správně dekódované kódy aktivita/nazev
    feat = _polygon_feature(15.02, 49.02, aktivita=1, nazev=1000)
    mocker.patch("engine.ki.datasources.landslides.query_layer", return_value={"features": [feat]})
    finding, raw = await landslides.get_landslide_finding(15.0, 49.0)

    assert finding.probability_level is None
    assert "aktivní" in finding.fact
    assert "sesouvání" in finding.fact
    assert "m (" in finding.fact  # vzdálenost v metrech uvedená
    assert raw == [feat]


@pytest.mark.asyncio
async def test_object_inside_deformation_polygon(mocker):
    feat = _polygon_feature(15.0, 49.0, aktivita=2, nazev=110, offset=0.01)
    mocker.patch("engine.ki.datasources.landslides.query_layer", return_value={"features": [feat]})
    finding, raw = await landslides.get_landslide_finding(15.0, 49.0)

    assert "leží v evidované" in finding.fact
    assert "dočasně uklidněné" in finding.fact


@pytest.mark.asyncio
async def test_query_error_gives_data_unavailable(mocker):
    async def raise_error(*a, **k):
        raise landslides.ArcGisQueryError("boom")

    mocker.patch("engine.ki.datasources.landslides.query_layer", side_effect=raise_error)
    finding, raw = await landslides.get_landslide_finding(15.0, 49.0)

    assert finding.data_unavailable is True
    assert raw == []
