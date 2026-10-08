import pytest

from engine.ki.datasources import egms


@pytest.mark.asyncio
async def test_missing_token_gives_honest_data_unavailable(monkeypatch):
    monkeypatch.delenv("CLMS_API_TOKEN", raising=False)
    finding, raw = await egms.get_egms_finding(15.0, 49.0)

    assert finding.data_unavailable is True
    assert finding.fact == "Nelze určit."
    assert "CLMS_API_TOKEN" in finding.caveat
    assert raw == []
