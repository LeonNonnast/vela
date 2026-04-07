"""AC-2: Health Check Endpoint Tests."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastmcp import FastMCP



def _async_client(app):
    """Create httpx.AsyncClient with ASGI transport."""
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _make_health_server() -> FastMCP:
    """Create a minimal server with health routes only."""
    server = FastMCP("TestVela")

    from starlette.requests import Request
    from starlette.responses import JSONResponse

    @server.custom_route(path="/health", methods=["GET"], name="health")
    async def health_check(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "vela"})

    @server.custom_route(path="/health/live", methods=["GET"], name="health_live")
    async def liveness_check(request: Request) -> JSONResponse:
        return JSONResponse({"status": "alive"})

    @server.custom_route(path="/health/ready", methods=["GET"], name="health_ready")
    async def readiness_check(request: Request) -> JSONResponse:
        from src.shared.db.database import check_db_health

        is_healthy = await check_db_health()
        if is_healthy:
            return JSONResponse({"status": "ready", "database": "connected"})
        return JSONResponse(
            {"status": "not_ready", "database": "disconnected"},
            status_code=503,
        )

    return server


class TestHealthEndpoints:
    async def test_health_returns_ok(self):
        server = _make_health_server()
        app = server.http_app()
        async with _async_client(app) as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data == {"status": "ok", "service": "vela"}

    async def test_liveness_returns_alive(self):
        server = _make_health_server()
        app = server.http_app()
        async with _async_client(app) as client:
            resp = await client.get("/health/live")
            assert resp.status_code == 200
            assert resp.json() == {"status": "alive"}

    @patch("src.shared.db.database.check_db_health", new_callable=AsyncMock, return_value=True)
    async def test_readiness_healthy(self, mock_health):
        server = _make_health_server()
        app = server.http_app()
        async with _async_client(app) as client:
            resp = await client.get("/health/ready")
            assert resp.status_code == 200
            data = resp.json()
            assert data == {"status": "ready", "database": "connected"}

    @patch("src.shared.db.database.check_db_health", new_callable=AsyncMock, return_value=False)
    async def test_readiness_unhealthy(self, mock_health):
        server = _make_health_server()
        app = server.http_app()
        async with _async_client(app) as client:
            resp = await client.get("/health/ready")
            assert resp.status_code == 503
            data = resp.json()
            assert data == {"status": "not_ready", "database": "disconnected"}

    @patch("src.shared.db.database.check_db_health", new_callable=AsyncMock, return_value=True)
    async def test_readiness_response_structure(self, mock_health):
        server = _make_health_server()
        app = server.http_app()
        async with _async_client(app) as client:
            resp = await client.get("/health/ready")
            data = resp.json()
            assert "status" in data
            assert "database" in data
