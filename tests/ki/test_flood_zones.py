import pytest

from engine.ki.datasources import flood_zones


def _fc(n_features: int) -> dict:
    return {"features": [{"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [[[0, 0]]]}} for _ in range(n_features)]}


@pytest.mark.asyncio
async def test_object_in_q5_gives_level_4(mocker):
    async def fake_query(base_url, layer_id, geom, **kwargs):
        return _fc(1) if layer_id == flood_zones.LAYER_Q5 else (
            _fc(0) if layer_id == flood_zones.LAYER_AKTIVNI_ZONA else _fc(1)
        )

    mocker.patch("engine.ki.datasources.flood_zones.query_layer", side_effect=fake_query)
    finding, raw = await flood_zones.get_flood_finding(15.0, 49.0)

    assert finding.probability_level == 4
    assert "Q5" in finding.fact
    assert finding.data_unavailable is False


@pytest.mark.asyncio
async def test_object_in_q20_only_is_borderline(mocker):
    async def fake_query(base_url, layer_id, geom, **kwargs):
        if layer_id == flood_zones.LAYER_Q5:
            return _fc(0)
        if layer_id == flood_zones.LAYER_Q20:
            return _fc(1)
        if layer_id == flood_zones.LAYER_Q100:
            return _fc(1)
        return _fc(0)

    mocker.patch("engine.ki.datasources.flood_zones.query_layer", side_effect=fake_query)
    finding, raw = await flood_zones.get_flood_finding(15.0, 49.0)

    assert finding.probability_level == 2
    assert finding.is_borderline is True
    assert finding.borderline_alternative_level == 1


@pytest.mark.asyncio
async def test_object_outside_all_zones(mocker):
    mocker.patch("engine.ki.datasources.flood_zones.query_layer", side_effect=lambda *a, **k: _fc(0))
    finding, raw = await flood_zones.get_flood_finding(15.0, 49.0)

    assert finding.probability_level == 1
    assert "mimo" in finding.fact.lower()


@pytest.mark.asyncio
async def test_query_error_gives_data_unavailable(mocker):
    async def raise_error(*a, **k):
        raise flood_zones.ArcGisQueryError("boom")

    mocker.patch("engine.ki.datasources.flood_zones.query_layer", side_effect=raise_error)
    finding, raw = await flood_zones.get_flood_finding(15.0, 49.0)

    assert finding.data_unavailable is True
    assert finding.probability_level is None
    assert raw == []
