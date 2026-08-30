"""
Sdílený OAuth2 client_credentials token provider pro CDSE služby
(Sentinel Hub Statistical API — Sentinel-1 i Sentinel-2 běží na stejné
identitě). Extrahováno z engine/datasources/sentinel1_cdse.py při přidání
Sentinel2NDVISource, ať se token-fetch nekopíruje potřetí.
"""

import time

import httpx


class CDSETokenProvider:
    def __init__(self, client_id: str, client_secret: str, token_url: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_url = token_url
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def get_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires_at - 30:
            return self._token

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                self._token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            resp.raise_for_status()
            payload = resp.json()

        self._token = payload["access_token"]
        self._token_expires_at = time.monotonic() + float(payload.get("expires_in", 300))
        return self._token
