"""
Bezpečnostní audit 2026-10-14: fail-closed autentizace a validace vstupů.
Žádné síťové volání - všechny requesty skončí na auth/validaci dřív, než
by route sáhla na CDSE nebo NASA POWER.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from main import app
from utils.config import settings

SECRET = "test-secret-0123456789abcdef"

# ~1 ha čtverec u Havlíčkova Brodu
SMALL_POLYGON = {
    "type": "Polygon",
    "coordinates": [[[15.58, 49.60], [15.5814, 49.60], [15.5814, 49.6009], [15.58, 49.6009], [15.58, 49.60]]],
}
# ~7 km x 7 km = ~5000 ha, nad limitem 2000 ha
HUGE_POLYGON = {
    "type": "Polygon",
    "coordinates": [[[15.5, 49.6], [15.6, 49.6], [15.6, 49.665], [15.5, 49.665], [15.5, 49.6]]],
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "NEXT_JS_SECRET", SECRET)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ENGINE_ALLOW_NO_AUTH", False)
    return TestClient(app)


def _post(client, path, body, secret=SECRET):
    headers = {"X-Internal-Secret": secret} if secret is not None else {}
    return client.post(path, json=body, headers=headers)


def _radiometric(**overrides):
    body = {"geometry": SMALL_POLYGON, "date_start": "2026-09-01", "date_end": "2026-09-14"}
    body.update(overrides)
    return body


class TestAuth:
    def test_missing_secret_config_fails_closed(self, client, monkeypatch):
        # Dřív: prázdný NEXT_JS_SECRET + ENVIRONMENT != production = API bez autentizace.
        monkeypatch.setattr(settings, "NEXT_JS_SECRET", "")
        monkeypatch.setattr(settings, "ENVIRONMENT", "development")
        assert _post(client, "/api/analyze/radiometric", _radiometric(), secret=None).status_code == 503

    def test_dev_bypass_needs_explicit_flag(self, client, monkeypatch):
        monkeypatch.setattr(settings, "NEXT_JS_SECRET", "")
        monkeypatch.setattr(settings, "ENVIRONMENT", "development")
        monkeypatch.setattr(settings, "ENGINE_ALLOW_NO_AUTH", True)
        # Auth projde, request spadne až na validaci (422), ne na 401/503.
        resp = _post(client, "/api/analyze/radiometric", _radiometric(date_end="nope"), secret=None)
        assert resp.status_code == 422

    def test_dev_bypass_ignored_in_production(self, client, monkeypatch):
        monkeypatch.setattr(settings, "NEXT_JS_SECRET", "")
        monkeypatch.setattr(settings, "ENGINE_ALLOW_NO_AUTH", True)
        assert _post(client, "/api/analyze/radiometric", _radiometric(), secret=None).status_code == 503

    @pytest.mark.parametrize("path", ["/api/analyze/radiometric", "/api/imagery/truecolor", "/api/agroclimate/summary"])
    def test_wrong_or_missing_secret_rejected(self, client, path):
        assert _post(client, path, {}, secret="wrong").status_code == 401
        assert _post(client, path, {}, secret=None).status_code == 401


class TestValidation:
    @pytest.mark.parametrize("overrides", [
        {"date_end": "2026-13-45"},
        {"date_end": "20260914"},
        {"date_end": (date.today() + timedelta(days=10)).isoformat()},
        {"date_start": "2026-09-14", "date_end": "2026-09-01"},
        {"date_start": "2024-01-01", "date_end": "2026-01-01"},
        {"date_start": "2010-01-01", "date_end": "2010-02-01"},
        {"geometry": HUGE_POLYGON},
        {"geometry": {"type": "MultiPolygon", "coordinates": [SMALL_POLYGON["coordinates"]]}},
        {"geometry": {"type": "Polygon", "coordinates": [[[200, 49], [15, 49], [15, 50], [200, 49]]]}},
        {"geometry": {"type": "Polygon", "coordinates": [[[15, 49], [15, 50], [15, 49]]]}},
        {"orbit_direction": "SIDEWAYS"},
    ])
    def test_radiometric_rejects_bad_input(self, client, overrides):
        assert _post(client, "/api/analyze/radiometric", _radiometric(**overrides)).status_code == 422

    def test_truecolor_has_aoi_limit(self, client):
        # Dřív limit plochy platil jen pro Sentinel-1.
        body = {"geometry": HUGE_POLYGON, "date_start": "2026-09-01", "date_end": "2026-09-14"}
        assert _post(client, "/api/imagery/truecolor", body).status_code == 422

    @pytest.mark.parametrize("overrides", [
        {"lookback_years": 100},
        {"lookback_years": 0},
        {"gdd_base_temp": 99},
        {"as_of_date": "2026-01-01", "season_start": "2026-06-01"},
    ])
    def test_agroclimate_rejects_bad_input(self, client, overrides):
        body = {"geometry": SMALL_POLYGON, "season_start": "2026-01-01", "as_of_date": "2026-09-01"}
        body.update(overrides)
        assert _post(client, "/api/agroclimate/summary", body).status_code == 422

    def test_valid_body_passes_validation(self):
        # Kladný případ přímo na modelu - přes HTTP by šel na CDSE.
        from api.models import RadiometricAnalysisRequest
        req = RadiometricAnalysisRequest(**_radiometric())
        assert req.date_end == "2026-09-14"
