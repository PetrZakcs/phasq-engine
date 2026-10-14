import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    CDSE_CLIENT_ID = os.environ.get("CDSE_CLIENT_ID", "")
    CDSE_CLIENT_SECRET = os.environ.get("CDSE_CLIENT_SECRET", "")
    CDSE_TOKEN_URL = os.environ.get(
        "CDSE_TOKEN_URL",
        "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
    )
    CDSE_STATS_API_URL = os.environ.get(
        "CDSE_STATS_API_URL", "https://sh.dataspace.copernicus.eu/api/v1/statistics"
    )

    NEXT_JS_SECRET = os.environ.get("NEXT_JS_SECRET", "")
    ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")
    # Jen pro lokální vývoj bez secretu - viz api/middleware.py (fail-closed).
    ENGINE_ALLOW_NO_AUTH = os.environ.get("ENGINE_ALLOW_NO_AUTH", "") == "1"

    @property
    def cdse_configured(self) -> bool:
        return bool(self.CDSE_CLIENT_ID and self.CDSE_CLIENT_SECRET)


settings = Settings()
