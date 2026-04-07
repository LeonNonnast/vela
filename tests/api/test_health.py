"""API Health endpoint tests."""

from unittest.mock import AsyncMock, patch

import pytest


class TestAPIHealth:
    async def test_health_returns_ok(self, api_client):
        async with api_client as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok", "service": "vela-api"}

    async def test_liveness(self, api_client):
        async with api_client as client:
            resp = await client.get("/health/live")
            assert resp.status_code == 200
            assert resp.json() == {"status": "alive"}

    @patch("src.shared.db.database.check_db_health", new_callable=AsyncMock, return_value=True)
    async def test_readiness_healthy(self, mock_health, api_client):
        async with api_client as client:
            resp = await client.get("/health/ready")
            assert resp.status_code == 200
            assert resp.json() == {"status": "ready", "database": "connected"}

    @patch("src.shared.db.database.check_db_health", new_callable=AsyncMock, return_value=False)
    async def test_readiness_unhealthy(self, mock_health, api_client):
        async with api_client as client:
            resp = await client.get("/health/ready")
            assert resp.status_code == 503
