"""
Sdílený OAuth2 client_credentials token provider pro CDSE služby
(Sentinel Hub Statistical API — Sentinel-1 i Sentinel-2 běží na stejné
identitě). Extrahováno z engine/datasources/sentinel1_cdse.py při přidání
Sentinel2NDVISource, ať se token-fetch nekopíruje potřetí.
"""

import asyncio
import time

import httpx

# Sdílené instance napříč requesty (audit 2026-10-14): datasource se
# vytváří per-request, takže každý request dřív stahoval nový OAuth token
# (S1 i S2 zvlášť) - zbytečná latence a riziko rate limitu CDSE identity.
_shared: dict[tuple[str, str], "CDSETokenProvider"] = {}


class CDSETokenProvider:
    @classmethod
    def shared(cls, client_id: str, client_secret: str, token_url: str) -> "CDSETokenProvider":
        key = (client_id, token_url)
        provider = _shared.get(key)
        if provider is None or provider._client_secret != client_secret:
            provider = cls(client_id, client_secret, token_url)
            _shared[key] = provider
        return provider

    def __init__(self, client_id: str, client_secret: str, token_url: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_url = token_url
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._lock = asyncio.Lock()

    def _valid_token(self) -> str | None:
        if self._token and time.monotonic() < self._token_expires_at - 30:
            return self._token
        return None

    async def get_token(self) -> str:
        if token := self._valid_token():
            return token
        async with self._lock:  # souběžné requesty nestahují token každý zvlášť
            if token := self._valid_token():
                return token
            return await self._fetch_token()

    async def _fetch_token(self) -> str:
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
