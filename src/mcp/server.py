"""Vela MCP Server — Entry Point.

Clean MCP server: tools, prompts, resources, stdio + HTTP transport.
No UI, no REST API endpoints (those live in src/api/).

Usage:
    uv run python -m src.mcp.server            # HTTP on port 8000
    uv run python -m src.mcp.server --stdio     # stdio transport
    uv run uvicorn src.mcp.server:app --port 8000
"""

import logging
import os
import sys

import structlog
import uvicorn
from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

# Redirect all logging to stderr (required for stdio transport — stdout is for JSON-RPC)
logging.basicConfig(stream=sys.stderr, level=logging.INFO, force=True)
structlog.configure(
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
)

load_dotenv()

from src.shared.config import (  # noqa: E402
    APP_BASE_URL,
    APP_ENV,
    HOST,
    MCP_PORT,
    SENTRY_DSN,
    VELA_MODULES,
)

logger = structlog.get_logger()

# Initialize Sentry if configured
if SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(dsn=SENTRY_DSN, environment=APP_ENV)

# Create FastMCP server
mcp = FastMCP(
    name="Vela",
    instructions="Vela MCP Server — persistent context, memory, and workflow engine for AI assistants.",
    on_duplicate="replace",
)

# --- Module Filter Middleware (per-request via X-Vela-Modules header) ---
from src.mcp.middleware.module_filter_middleware import VelaModuleFilterMiddleware  # noqa: E402

mcp.add_middleware(VelaModuleFilterMiddleware())

# --- Register All Modules ---
from src.mcp.module_registry import register_all_modules  # noqa: E402

register_all_modules(mcp)

if VELA_MODULES:
    logger.info("vela.module_filter.active", patterns=VELA_MODULES)

# --- Initialize MCP Orchestrator ---
from src.shared.services.mcp_orchestrator import MCPOrchestrator  # noqa: E402

orchestrator = MCPOrchestrator.from_config()


# --- Health Check (for Docker) ---
@mcp.custom_route(path="/health", methods=["GET"], name="health")
async def health_check(request: Request) -> JSONResponse:
    """Basic health check."""
    return JSONResponse({"status": "ok", "service": "vela-mcp"})


# --- Ensure DB tables on startup ---
from src.shared.db.database import ensure_tables_sync  # noqa: E402

try:
    ensure_tables_sync()
    logger.info("vela.db_tables_ensured")
except Exception as e:
    logger.error("vela.db_tables_failed", error=str(e))

# --- Create ASGI App ---
logger.info("vela.mcp.startup", env=APP_ENV, base_url=APP_BASE_URL)
app = mcp.http_app()


# --- stdio support ---
if __name__ == "__main__":
    if "--stdio" in sys.argv or os.getenv("MCP_TRANSPORT") == "stdio":
        mcp.run(transport="stdio", show_banner=False)
    else:
        uvicorn.run(
            "src.mcp.server:app",
            host=HOST,
            port=MCP_PORT,
            reload=(APP_ENV == "development"),
        )
