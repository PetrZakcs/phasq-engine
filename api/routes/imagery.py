"""
Mapový podklad — Sentinel-2 true-color přes CDSE, náhrada za Esri
World_Imagery dlaždice (viz docs/ADR-005-free-data-sources.md — Esri
komerční použití explicitně zakazuje bez vlastní licence).
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response

from api.middleware import verify_internal_secret
from api.models import TrueColorImageRequest
from engine.datasources.sentinel2_truecolor import Sentinel2TrueColorSource
from utils.config import settings

router = APIRouter()


@router.post("/imagery/truecolor", dependencies=[Depends(verify_internal_secret)])
async def truecolor_image(req: TrueColorImageRequest):
    if not settings.cdse_configured:
        raise HTTPException(status_code=503, detail="CDSE credentials nejsou nastaveny.")

    source = Sentinel2TrueColorSource(
        client_id=settings.CDSE_CLIENT_ID,
        client_secret=settings.CDSE_CLIENT_SECRET,
        token_url=settings.CDSE_TOKEN_URL,
        stats_api_url=settings.CDSE_STATS_API_URL,
    )

    try:
        png_bytes = await source.get_truecolor_png(req.geometry, req.date_start, req.date_end)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"CDSE Process API error {e.response.status_code}: {e.response.text[:300]}")

    return Response(content=png_bytes, media_type="image/png")
