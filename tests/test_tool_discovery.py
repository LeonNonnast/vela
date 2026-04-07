"""Tool Discovery Tests — V1 full platform (11 tools)."""

import json
import os
import tempfile

import pytest
import yaml
from fastmcp import Client, FastMCP

from src.mcp.modules.context_module import ContextModule
from src.mcp.modules.memory_module import MemoryModule
from src.mcp.modules.workflow_module import WorkflowModule
from src.mcp.modules.agent_module import AgentModule
from src.mcp.modules.vela_module import AdminModule
from src.shared.services.project_service import ProjectService
from src.shared.services.memory_service import MemoryService
from tests.conftest import reset_singleton

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from src.shared.db.base import Base


def _make_test_dirs():
    """Create temp workflow and agent dirs for testing."""
    wf_dir = tempfile.mkdtemp()
    agent_dir = tempfile.mkdtemp()

    wf_data = {
        "id": "test-wf",
        "name": "Test",
        "steps": [{"id": "s1", "type": "freeform", "prompt": "go"}],
    }
    with open(os.path.join(wf_dir, "test-wf@1.0.0.yaml"), "w") as f:
        yaml.dump(wf_data, f)

    agent_data = {"id": "test-agent", "name": "Test Agent", "persona": "test"}
    with open(os.path.join(agent_dir, "test-agent.yaml"), "w") as f:
        yaml.dump(agent_data, f)

    return wf_dir, agent_dir


async def _make_full_server():
    """Create a test server with all V1 modules registered."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    wf_dir, agent_dir = _make_test_dirs()

    server = FastMCP("TestVela")

    reset_singleton(ContextModule)
    reset_singleton(MemoryModule)
    reset_singleton(WorkflowModule)
    reset_singleton(AgentModule)
    reset_singleton(AdminModule)

    import src.mcp.modules.workflow_module as wf_mod
    import src.mcp.modules.agent_module as agent_mod
    import src.shared.services.filesystem_loader as fs_loader

    wf_mod.VELA_WORKFLOWS_DIR = wf_dir
    agent_mod.VELA_AGENTS_DIR = agent_dir
    fs_loader.VELA_MODULES_DIR = "/nonexistent"
    project_service = ProjectService(session_factory)
    memory_service = MemoryService(session_factory)

    ContextModule.construct(mcp=server, project_service=project_service)
    MemoryModule.construct(mcp=server, memory_service=memory_service)
    WorkflowModule.construct(mcp=server, session_factory=session_factory)
    AgentModule.construct(mcp=server)
    AdminModule.construct(mcp=server, session_factory=session_factory)

    return server, engine


EXPECTED_TOOLS = {
    # Context (3)
    "vela_set_project",
    "vela_get_project",
    "vela_list_projects",
    # Memory (4)
    "vela_remember",
    "vela_recall",
    "vela_get_memory",
    "vela_forget",
    # Workflow (3)
    "vela_advance_workflow",
    "vela_workflow_status",
    "vela_list_workflows",
    # Agent (1)
    "vela_list_agents",
    # Admin (3)
    "vela_validate",
    "vela_save",
    "vela_status",
}


class TestToolDiscovery:
    async def test_expected_tool_count(self):
        """V1 should register exactly 14 tools."""
        server, engine = await _make_full_server()
        async with Client(server) as client:
            tools = await client.list_tools()
            assert len(tools) == 14
        await engine.dispose()

    async def test_tool_names_exact_match(self):
        """All V1 tools should be present."""
        server, engine = await _make_full_server()
        async with Client(server) as client:
            tools = await client.list_tools()
            names = {t.name for t in tools}
            assert names == EXPECTED_TOOLS
        await engine.dispose()

    async def test_all_tools_have_descriptions(self):
        server, engine = await _make_full_server()
        async with Client(server) as client:
            tools = await client.list_tools()
            assert all(t.description for t in tools)
        await engine.dispose()

    async def test_no_tools_without_modules(self):
        server = FastMCP("TestVela")
        async with Client(server) as client:
            tools = await client.list_tools()
            assert len(tools) == 0

    async def test_prompts_registered(self):
        """Workflow and agent prompts should be registered."""
        server, engine = await _make_full_server()
        async with Client(server) as client:
            prompts = await client.list_prompts()
            names = {p.name for p in prompts}
            assert "vela_test-wf" in names
            assert "vela_agent_test-agent" in names
        await engine.dispose()
