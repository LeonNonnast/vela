"""Health check endpoints for Vela API."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> JSONResponse:
    """Basic health check."""
    return JSONResponse({"status": "ok", "service": "vela-api"})


@router.get("/health/live")
async def liveness_check() -> JSONResponse:
    """Liveness probe for container orchestration."""
    return JSONResponse({"status": "alive"})


@router.get("/health/ready")
async def readiness_check() -> JSONResponse:
    """Readiness probe - checks database connectivity."""
    from src.shared.db.database import check_db_health

    is_healthy = await check_db_health()
    if is_healthy:
        return JSONResponse({"status": "ready", "database": "connected"})
    return JSONResponse(
        {"status": "not_ready", "database": "disconnected"},
        status_code=503,
    )
