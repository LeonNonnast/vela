"""Fixtures for API tests."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.app import app


@pytest.fixture
def api_client():
    """Create an httpx AsyncClient for the FastAPI app."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")
