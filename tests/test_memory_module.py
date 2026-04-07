"""Memory Module Tests — vela_remember, vela_recall, vela_get_memory, vela_forget."""

import json

import pytest
from fastmcp import Client, FastMCP
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.shared.db.base import Base
from src.mcp.modules.context_module import ContextModule
from src.mcp.modules.memory_module import MemoryModule
from tests.conftest import reset_singleton


def _extract_text(result):
    """Extract text from a call_tool result."""
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        return result[0].text
    if hasattr(result, "content"):
        content = result.content
        if isinstance(content, list):
            return content[0].text
        return content
    if hasattr(result, "text"):
        return result.text
    return str(result)


def _make_memory_server(session_factory):
    """Create a test server with ContextModule + MemoryModule."""
    from src.shared.services.memory_service import MemoryService
    from src.shared.services.project_service import ProjectService

    server = FastMCP("TestVela")

    reset_singleton(ContextModule)
    reset_singleton(MemoryModule)

    project_service = ProjectService(session_factory)
    memory_service = MemoryService(session_factory)
    ContextModule.construct(mcp=server, project_service=project_service)
    MemoryModule.construct(mcp=server, memory_service=memory_service)
    return server


@pytest.fixture
async def mem_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def mem_session_factory(mem_engine):
    return async_sessionmaker(mem_engine, expire_on_commit=False)


class TestMemoryModule:
    async def test_remember_creates_memory(self, mem_session_factory):
        server = _make_memory_server(mem_session_factory)
        async with Client(server) as client:
            raw = await client.call_tool("vela_remember", {
                "title": "Use FastMCP",
                "content": "We use FastMCP 3.0 for MCP server.",
                "category": "decision",
            })
            result = json.loads(_extract_text(raw))
            assert result["title"] == "Use FastMCP"
            assert result["category"] == "decision"
            assert "id" in result

    async def test_remember_with_tags(self, mem_session_factory):
        server = _make_memory_server(mem_session_factory)
        async with Client(server) as client:
            raw = await client.call_tool("vela_remember", {
                "title": "PEP8",
                "content": "Follow PEP8 style guide.",
                "category": "convention",
                "tags": ["python", "style"],
            })
            result = json.loads(_extract_text(raw))
            assert result["tags"] == ["python", "style"]

    async def test_remember_with_project(self, mem_session_factory):
        server = _make_memory_server(mem_session_factory)
        async with Client(server) as client:
            # Create project first
            await client.call_tool("vela_set_project", {"slug": "test-proj", "name": "Test"})
            raw = await client.call_tool("vela_remember", {
                "title": "Scoped memory",
                "content": "This is project-scoped.",
                "category": "fact",
                "project_slug": "test-proj",
            })
            result = json.loads(_extract_text(raw))
            assert result["project_id"] is not None

    async def test_remember_invalid_category(self, mem_session_factory):
        server = _make_memory_server(mem_session_factory)
        async with Client(server) as client:
            raw = await client.call_tool("vela_remember", {
                "title": "Bad",
                "content": "Bad category",
                "category": "invalid",
            })
            result = json.loads(_extract_text(raw))
            assert "error" in result

    async def test_remember_invalid_project(self, mem_session_factory):
        server = _make_memory_server(mem_session_factory)
        async with Client(server) as client:
            raw = await client.call_tool("vela_remember", {
                "title": "Bad",
                "content": "Bad project",
                "category": "fact",
                "project_slug": "nonexistent",
            })
            result = json.loads(_extract_text(raw))
            assert result["error"] == "Project not found"

    async def test_recall_returns_index(self, mem_session_factory):
        server = _make_memory_server(mem_session_factory)
        async with Client(server) as client:
            await client.call_tool("vela_remember", {
                "title": "Memory A",
                "content": "Content A is detailed.",
                "category": "insight",
            })
            raw = await client.call_tool("vela_recall", {})
            result = json.loads(_extract_text(raw))
            assert len(result) == 1
            assert result[0]["title"] == "Memory A"
            # recall should NOT include content
            assert "content" not in result[0]

    async def test_recall_by_category(self, mem_session_factory):
        server = _make_memory_server(mem_session_factory)
        async with Client(server) as client:
            await client.call_tool("vela_remember", {
                "title": "Decision 1",
                "content": "D1",
                "category": "decision",
            })
            await client.call_tool("vela_remember", {
                "title": "Fact 1",
                "content": "F1",
                "category": "fact",
            })
            raw = await client.call_tool("vela_recall", {"category": "decision"})
            result = json.loads(_extract_text(raw))
            assert len(result) == 1
            assert result[0]["category"] == "decision"

    async def test_recall_by_query(self, mem_session_factory):
        server = _make_memory_server(mem_session_factory)
        async with Client(server) as client:
            await client.call_tool("vela_remember", {
                "title": "FastMCP decision",
                "content": "Use FastMCP.",
                "category": "decision",
            })
            await client.call_tool("vela_remember", {
                "title": "Database choice",
                "content": "Use SQLite.",
                "category": "decision",
            })
            raw = await client.call_tool("vela_recall", {"query": "FastMCP"})
            result = json.loads(_extract_text(raw))
            assert len(result) == 1
            assert "FastMCP" in result[0]["title"]

    async def test_recall_by_tags(self, mem_session_factory):
        server = _make_memory_server(mem_session_factory)
        async with Client(server) as client:
            await client.call_tool("vela_remember", {
                "title": "Tagged mem",
                "content": "Has tags.",
                "category": "convention",
                "tags": ["python", "style"],
            })
            await client.call_tool("vela_remember", {
                "title": "No tags",
                "content": "No tags here.",
                "category": "fact",
            })
            raw = await client.call_tool("vela_recall", {"tags": ["python"]})
            result = json.loads(_extract_text(raw))
            assert len(result) == 1
            assert result[0]["title"] == "Tagged mem"

    async def test_recall_by_project(self, mem_session_factory):
        server = _make_memory_server(mem_session_factory)
        async with Client(server) as client:
            await client.call_tool("vela_set_project", {"slug": "proj-x", "name": "X"})
            await client.call_tool("vela_remember", {
                "title": "Scoped",
                "content": "Project scoped.",
                "category": "fact",
                "project_slug": "proj-x",
            })
            await client.call_tool("vela_remember", {
                "title": "Global",
                "content": "Not scoped.",
                "category": "fact",
            })
            raw = await client.call_tool("vela_recall", {"project_slug": "proj-x"})
            result = json.loads(_extract_text(raw))
            assert len(result) == 1
            assert result[0]["title"] == "Scoped"

    async def test_recall_with_limit(self, mem_session_factory):
        server = _make_memory_server(mem_session_factory)
        async with Client(server) as client:
            for i in range(5):
                await client.call_tool("vela_remember", {
                    "title": f"Mem {i}",
                    "content": f"Content {i}",
                    "category": "fact",
                })
            raw = await client.call_tool("vela_recall", {"limit": 3})
            result = json.loads(_extract_text(raw))
            assert len(result) == 3

    async def test_get_memory_found(self, mem_session_factory):
        server = _make_memory_server(mem_session_factory)
        async with Client(server) as client:
            create_raw = await client.call_tool("vela_remember", {
                "title": "Get me",
                "content": "Full content here.",
                "category": "insight",
            })
            created = json.loads(_extract_text(create_raw))
            mem_id = created["id"]

            raw = await client.call_tool("vela_get_memory", {"id": mem_id})
            result = json.loads(_extract_text(raw))
            assert result["id"] == mem_id
            assert result["content"] == "Full content here."
            assert result["title"] == "Get me"

    async def test_get_memory_not_found(self, mem_session_factory):
        server = _make_memory_server(mem_session_factory)
        async with Client(server) as client:
            raw = await client.call_tool("vela_get_memory", {"id": "nonexistent"})
            result = json.loads(_extract_text(raw))
            assert result["error"] == "Memory not found"

    async def test_forget_deletes_memory(self, mem_session_factory):
        server = _make_memory_server(mem_session_factory)
        async with Client(server) as client:
            create_raw = await client.call_tool("vela_remember", {
                "title": "Delete me",
                "content": "Gone soon.",
                "category": "fact",
            })
            created = json.loads(_extract_text(create_raw))
            mem_id = created["id"]

            raw = await client.call_tool("vela_forget", {"id": mem_id})
            result = json.loads(_extract_text(raw))
            assert result["deleted"] is True

            # Verify it's gone
            raw = await client.call_tool("vela_get_memory", {"id": mem_id})
            result = json.loads(_extract_text(raw))
            assert result["error"] == "Memory not found"

    async def test_forget_not_found(self, mem_session_factory):
        server = _make_memory_server(mem_session_factory)
        async with Client(server) as client:
            raw = await client.call_tool("vela_forget", {"id": "nonexistent"})
            result = json.loads(_extract_text(raw))
            assert result["error"] == "Memory not found"

    async def test_tool_count(self, mem_session_factory):
        server = _make_memory_server(mem_session_factory)
        async with Client(server) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            assert "vela_remember" in tool_names
            assert "vela_recall" in tool_names
            assert "vela_get_memory" in tool_names
            assert "vela_forget" in tool_names
