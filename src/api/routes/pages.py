"""Page routes — landing page and documentation."""

import os

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["pages"])

_STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
_DOCS_DIR = os.path.join(_STATIC_DIR, "docs")


@router.get("/", response_class=HTMLResponse)
async def landing_page() -> HTMLResponse:
    """Serve the Vela landing page."""
    path = os.path.join(_STATIC_DIR, "landing.html")
    with open(path, "r") as f:
        return HTMLResponse(f.read())


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page() -> HTMLResponse:
    """Serve the Vela dashboard."""
    path = os.path.join(_STATIC_DIR, "dashboard.html")
    with open(path, "r") as f:
        return HTMLResponse(f.read())


@router.get("/dashboard/runs/{run_id}", response_class=HTMLResponse)
async def run_detail_page(run_id: str) -> HTMLResponse:
    """Serve the run detail page."""
    path = os.path.join(_STATIC_DIR, "run-detail.html")
    with open(path, "r") as f:
        return HTMLResponse(f.read())


@router.get("/docs", response_class=HTMLResponse)
async def docs_index() -> HTMLResponse:
    """Serve the documentation index page."""
    path = os.path.join(_DOCS_DIR, "index.html")
    with open(path, "r") as f:
        return HTMLResponse(f.read())


@router.get("/docs/tools", response_class=HTMLResponse)
async def docs_tools() -> HTMLResponse:
    """Serve the MCP Tools reference page."""
    path = os.path.join(_DOCS_DIR, "tools.html")
    with open(path, "r") as f:
        return HTMLResponse(f.read())


@router.get("/docs/sdk", response_class=HTMLResponse)
async def docs_sdk() -> HTMLResponse:
    """Serve the SDK & API reference page."""
    path = os.path.join(_DOCS_DIR, "sdk.html")
    with open(path, "r") as f:
        return HTMLResponse(f.read())
