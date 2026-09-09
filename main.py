from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import agroclimate, analysis, health, imagery
from utils.config import settings

app = FastAPI(title="phasq-engine", version="0.1.0")

# Security checklist (master_plan.md 5.3): CORS whitelist jen na app.phasq.com,
# nikdy "*". Pro lokální dev povolen i localhost:3000.
_allowed_origins = ["https://app.phasq.com"]
if settings.ENVIRONMENT != "production":
    _allowed_origins.append("http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(analysis.router, prefix="/api")
app.include_router(agroclimate.router, prefix="/api")
app.include_router(imagery.router, prefix="/api")
