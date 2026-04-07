"""Context Module Tests — vela_set_project, vela_get_project, vela_list_projects."""

import json

import pytest
from fastmcp import Client, FastMCP

from src.shared.db.base import Base
from src.shared.db.models import Project
from src.mcp.modules.context_module import ContextModule
from tests.conftest import reset_singleton

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def _extract_text(result):
    """Extract text from a call_tool result, handling various return types."""
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        return result[0].text
    # CallToolResult or similar
    if hasattr(result, "content"):
        content = result.content
        if isinstance(content, list):
            return content[0].text
        return content
    if hasattr(result, "text"):
        return result.text
    return str(result)


def _make_context_server(session_factory):
    """Create a test server with ContextModule and patched DB."""
    from src.shared.services.project_service import ProjectService

    server = FastMCP("TestVela")
    reset_singleton(ContextModule)

    project_service = ProjectService(session_factory)
    ContextModule.construct(mcp=server, project_service=project_service)
    return server


@pytest.fixture
async def context_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def context_session_factory(context_engine):
    return async_sessionmaker(context_engine, expire_on_commit=False)


class TestContextModule:
    async def test_set_project_creates_new(self, context_session_factory):
        server = _make_context_server(context_session_factory)
        async with Client(server) as client:
            raw = await client.call_tool(
                "vela_set_project",
                {"slug": "my-proj", "name": "My Project"},
            )
            result = json.loads(_extract_text(raw))
            assert result["slug"] == "my-proj"
            assert result["name"] == "My Project"
            assert result["is_active"] is True

    async def test_set_project_upserts(self, context_session_factory):
        server = _make_context_server(context_session_factory)
        async with Client(server) as client:
            await client.call_tool(
                "vela_set_project",
                {"slug": "upsert-test", "name": "First"},
            )
            raw = await client.call_tool(
                "vela_set_project",
                {"slug": "upsert-test", "name": "Updated"},
            )
            result = json.loads(_extract_text(raw))
            assert result["name"] == "Updated"
            assert result["slug"] == "upsert-test"

    async def test_set_project_with_tech_stack(self, context_session_factory):
        server = _make_context_server(context_session_factory)
        async with Client(server) as client:
            raw = await client.call_tool(
                "vela_set_project",
                {
                    "slug": "tech-proj",
                    "name": "Tech Project",
                    "tech_stack": ["python", "fastmcp"],
                    "path": "/home/user/project",
                },
            )
            result = json.loads(_extract_text(raw))
            assert result["tech_stack"] == ["python", "fastmcp"]
            assert result["path"] == "/home/user/project"

    async def test_get_project_found(self, context_session_factory):
        server = _make_context_server(context_session_factory)
        async with Client(server) as client:
            await client.call_tool(
                "vela_set_project",
                {"slug": "find-me", "name": "Find Me"},
            )
            raw = await client.call_tool(
                "vela_get_project",
                {"slug": "find-me"},
            )
            result = json.loads(_extract_text(raw))
            assert result["slug"] == "find-me"
            assert result["name"] == "Find Me"

    async def test_get_project_not_found(self, context_session_factory):
        server = _make_context_server(context_session_factory)
        async with Client(server) as client:
            raw = await client.call_tool(
                "vela_get_project",
                {"slug": "nonexistent"},
            )
            result = json.loads(_extract_text(raw))
            assert result["error"] == "not found"

    async def test_list_projects_empty(self, context_session_factory):
        server = _make_context_server(context_session_factory)
        async with Client(server) as client:
            raw = await client.call_tool("vela_list_projects", {})
            result = json.loads(_extract_text(raw))
            assert result == []

    async def test_list_projects_returns_active(self, context_session_factory):
        server = _make_context_server(context_session_factory)
        async with Client(server) as client:
            await client.call_tool(
                "vela_set_project",
                {"slug": "proj-a", "name": "Project A"},
            )
            await client.call_tool(
                "vela_set_project",
                {"slug": "proj-b", "name": "Project B"},
            )
            raw = await client.call_tool("vela_list_projects", {})
            result = json.loads(_extract_text(raw))
            assert len(result) == 2
            slugs = {p["slug"] for p in result}
            assert slugs == {"proj-a", "proj-b"}

    async def test_set_project_update_path(self, context_session_factory):
        server = _make_context_server(context_session_factory)
        async with Client(server) as client:
            await client.call_tool(
                "vela_set_project",
                {"slug": "path-test", "name": "Path", "path": "/old"},
            )
            raw = await client.call_tool(
                "vela_set_project",
                {"slug": "path-test", "name": "Path", "path": "/new"},
            )
            result = json.loads(_extract_text(raw))
            assert result["path"] == "/new"

    async def test_set_project_conventions(self, context_session_factory):
        server = _make_context_server(context_session_factory)
        async with Client(server) as client:
            raw = await client.call_tool(
                "vela_set_project",
                {
                    "slug": "conv-proj",
                    "name": "Conv",
                    "conventions": ["PEP8", "type hints"],
                },
            )
            result = json.loads(_extract_text(raw))
            assert result["conventions"] == ["PEP8", "type hints"]

    async def test_tool_count(self, context_session_factory):
        server = _make_context_server(context_session_factory)
        async with Client(server) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            assert "vela_set_project" in tool_names
            assert "vela_get_project" in tool_names
            assert "vela_list_projects" in tool_names
