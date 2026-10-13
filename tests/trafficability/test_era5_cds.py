import pytest

from engine.trafficability.datasources import era5_cds


@pytest.mark.asyncio
async def test_missing_token_gives_honest_data_unavailable(monkeypatch):
    monkeypatch.delenv("CDS_API_KEY", raising=False)
    reading = await era5_cds.get_volumetric_moisture_reading(15.0, 49.0, as_of_date="2026-10-13")

    assert reading.data_unavailable is True
    assert reading.value is None
    assert "CDS_API_KEY" in reading.caveat


@pytest.mark.asyncio
async def test_retrieve_failure_gives_honest_data_unavailable_not_crash(monkeypatch):
    """Živě ověřeno 2026-10-13: platný token, ale neodsouhlasená licence
    dává 403 'required licences not accepted' - tenhle test hlídá, že se
    JAKÁKOLIV chyba z cdsapi promění na honest LayerReading, ne pád."""
    monkeypatch.setenv("CDS_API_KEY", "test-token")

    def boom(*args, **kwargs):
        raise RuntimeError("403 required licences not accepted")

    monkeypatch.setattr(era5_cds, "_retrieve_sync", boom)

    reading = await era5_cds.get_volumetric_moisture_reading(15.0, 49.0, as_of_date="2026-10-13")

    assert reading.data_unavailable is True
    assert reading.value is None
    assert "licenci" in reading.caveat.lower() or "licence" in reading.caveat.lower()
