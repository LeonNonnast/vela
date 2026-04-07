"""Pytest configuration and shared fixtures for Vela tests."""

import os

# Environment setup - must happen before any src imports
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastmcp import FastMCP
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.shared.db.base import Base


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def make_test_server() -> FastMCP:
    """Create a FastMCP test server."""
    server = FastMCP("TestVela")
    return server


def reset_singleton(cls: type) -> None:
    """Reset a module singleton so it can be re-constructed.

    Works with both the old _instance pattern and the new VelaModuleBase registry.
    """
    from src.mcp.modules.base import VelaModuleBase
    # Use the base class registry if the class uses it
    if isinstance(cls, type) and issubclass(cls, VelaModuleBase):
        cls.reset()
    elif hasattr(cls, '_instance'):
        cls._instance = None


def reset_all_singletons() -> None:
    """Reset all module singletons."""
    from src.mcp.modules.base import VelaModuleBase
    VelaModuleBase.reset_all()
    # Reset API layer's lazy registry instance
    from src.api.routes import repos as repos_mod
    repos_mod._registry = None


def make_db_session() -> MagicMock:
    """Create a mock async database session."""
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    session.delete = AsyncMock()
    session.refresh = AsyncMock()
    return session


def make_session_context(session: MagicMock) -> AsyncMock:
    """Create a mock async context manager wrapping a session."""
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def make_mock_mcp() -> MagicMock:
    """Create a mock FastMCP that captures tool and route registrations."""
    mock_mcp = MagicMock(spec=FastMCP)
    mock_mcp._tools: dict[str, Any] = {}
    mock_mcp._routes: dict[str, Any] = {}

    def capture_tool(**kwargs):
        def decorator(func):
            mock_mcp._tools[kwargs.get("name", func.__name__)] = {
                "handler": func,
                "kwargs": kwargs,
            }
            return func
        return decorator

    def capture_route(path: str, methods: list[str] | None = None, **kwargs):
        def decorator(func):
            mock_mcp._routes[path] = {
                "handler": func,
                "methods": methods or ["GET"],
                "kwargs": kwargs,
            }
            return func
        return decorator

    mock_mcp.tool = capture_tool
    mock_mcp.custom_route = capture_route
    return mock_mcp


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def async_engine():
    """Create an in-memory SQLite engine with all tables."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a real async database session for repository tests."""
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Singleton reset fixture
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset all module singletons before each test."""
    reset_all_singletons()
    yield
    reset_all_singletons()
