from fastapi import APIRouter

from utils.config import settings

router = APIRouter()


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "environment": settings.ENVIRONMENT,
        "cdse_configured": settings.cdse_configured,
    }
