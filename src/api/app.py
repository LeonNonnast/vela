"""Vela API — FastAPI web server.

Serves the landing page, dashboard, and REST API endpoints.

Usage:
    uv run uvicorn src.api.app:app --port 8001
"""

import os

import structlog
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

load_dotenv()

from src.shared.config import APP_ENV, SENTRY_DSN  # noqa: E402

logger = structlog.get_logger()

# Initialize Sentry if configured
if SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(dsn=SENTRY_DSN, environment=APP_ENV)

app = FastAPI(
    title="Vela API",
    description="Vela web dashboard and REST API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# --- Static Files ---
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

# --- Routes ---
from src.api.routes.health import router as health_router  # noqa: E402
from src.api.routes.repos import router as repos_router  # noqa: E402
from src.api.routes.workflows import router as workflows_router  # noqa: E402
from src.api.routes.pages import router as pages_router  # noqa: E402

app.include_router(health_router)
app.include_router(repos_router, prefix="/api")
app.include_router(workflows_router, prefix="/api")
app.include_router(pages_router)

# --- Ensure DB tables on startup ---
from src.shared.db.database import ensure_tables_sync  # noqa: E402

try:
    ensure_tables_sync()
    logger.info("vela.api.db_tables_ensured")
except Exception as e:
    logger.error("vela.api.db_tables_failed", error=str(e))

logger.info("vela.api.startup", env=APP_ENV)
