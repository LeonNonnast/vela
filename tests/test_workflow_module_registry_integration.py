"""Integration tests: Module Registry integration for all module types.

Verifies that workflows, agents, and resources pushed to DB modules are
discoverable by their respective modules via ModuleRegistryService.
"""

import json
import os
import tempfile
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
import yaml
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.shared.db.base import Base
from src.shared.db.models import CachedModuleFile, ModuleSource
from src.shared.services.module_registry_service import ModuleRegistryService
from src.mcp.modules.workflow_module import WorkflowModule
from src.mcp.modules.agent_module import AgentModule
from src.mcp.modules.resource_module import ResourceModule
from tests.conftest import make_mock_mcp, reset_singleton


DB_WORKFLOW_YAML = """\
id: db-workflow
version: "1.0.0"
name: DB Workflow
description: A workflow stored in the database
steps:
  - id: step-1
    type: freeform
    prompt: What would you like to do?
"""

FILESYSTEM_WORKFLOW_YAML = {
    "id": "fs-workflow",
    "version": "1.0.0",
    "name": "Filesystem Workflow",
    "description": "A workflow from the filesystem",
    "steps": [
        {"id": "step-1", "type": "freeform", "prompt": "Describe your idea"},
    ],
}

# Same ID as DB workflow but different content — filesystem should win
OVERRIDE_WORKFLOW_YAML = {
    "id": "db-workflow",
    "version": "1.0.0",
    "name": "Overridden DB Workflow",
    "description": "Filesystem override of db-workflow",
    "steps": [
        {"id": "step-1", "type": "freeform", "prompt": "Overridden prompt"},
    ],
}


def _make_session_factory(db_session):
    @asynccontextmanager
    async def _factory():
        yield db_session
    return _factory


@pytest.fixture
def tmpdir():
    """Create a temp directory for filesystem workflows."""
    d = tempfile.mkdtemp()
    yield d


@pytest.fixture
def registry():
    """Create a fresh ModuleRegistryService."""
    svc = ModuleRegistryService()
    return svc


class TestWorkflowModuleRegistryIntegration:
    """Verify WorkflowModule discovers workflows from DB via ModuleRegistryService."""

    async def test_db_workflow_found_via_get_workflow_async(self, db_session, registry, tmpdir):
        """A workflow pushed to DB should be found by _get_workflow_async."""
        factory = _make_session_factory(db_session)
        registry._session_factory = factory

        # Insert a DB module with a workflow
        source = ModuleSource(provider="db", owner="db", name="test-module", branch="main")
        db_session.add(source)
        await db_session.flush()

        cached = CachedModuleFile(
            source_id=source.id,
            file_type="workflow",
            file_path="workflows/db-workflow@1.0.0.yaml",
            content=DB_WORKFLOW_YAML,
            sha="abc123",
        )
        db_session.add(cached)
        await db_session.commit()

        # Create WorkflowModule with empty filesystem but with registry
        mcp = make_mock_mcp()
        with (
            patch("src.shared.config.VELA_MODULES_DIR", os.path.join(tmpdir, "modules")),
            patch("src.mcp.modules.workflow_module.VELA_WORKFLOWS_DIR", os.path.join(tmpdir, "workflows")),
        ):
            module = WorkflowModule(mcp=mcp, session_factory=factory, module_registry=registry)

            # Sync method should NOT find it (filesystem only)
            assert module._get_workflow("db-workflow") is None

            # Async method SHOULD find it (includes registry)
            wf = await module._get_workflow_async("db-workflow")
            assert wf is not None
            assert wf.id == "db-workflow"
            assert wf.name == "DB Workflow"

    async def test_get_all_workflows_merges_sources(self, db_session, registry, tmpdir):
        """_get_all_workflows merges filesystem and DB workflows."""
        factory = _make_session_factory(db_session)
        registry._session_factory = factory

        # Insert DB workflow
        source = ModuleSource(provider="db", owner="db", name="test-module", branch="main")
        db_session.add(source)
        await db_session.flush()

        cached = CachedModuleFile(
            source_id=source.id,
            file_type="workflow",
            file_path="workflows/db-workflow@1.0.0.yaml",
            content=DB_WORKFLOW_YAML,
            sha="abc123",
        )
        db_session.add(cached)
        await db_session.commit()

        # Create filesystem workflow
        wf_dir = os.path.join(tmpdir, "workflows")
        os.makedirs(wf_dir)
        with open(os.path.join(wf_dir, "fs-workflow@1.0.0.yaml"), "w") as f:
            yaml.dump(FILESYSTEM_WORKFLOW_YAML, f)

        mcp = make_mock_mcp()
        with (
            patch("src.shared.config.VELA_MODULES_DIR", os.path.join(tmpdir, "modules")),
            patch("src.mcp.modules.workflow_module.VELA_WORKFLOWS_DIR", wf_dir),
        ):
            module = WorkflowModule(mcp=mcp, session_factory=factory, module_registry=registry)

            all_wfs = await module._get_all_workflows()

            # Both should be present
            assert "db-workflow@1.0.0" in all_wfs
            assert "fs-workflow@1.0.0" in all_wfs
            assert all_wfs["db-workflow@1.0.0"].name == "DB Workflow"
            assert all_wfs["fs-workflow@1.0.0"].name == "Filesystem Workflow"

    async def test_filesystem_overrides_db_workflow(self, db_session, registry, tmpdir):
        """Filesystem workflow with same ID should override DB workflow."""
        factory = _make_session_factory(db_session)
        registry._session_factory = factory

        # Insert DB workflow
        source = ModuleSource(provider="db", owner="db", name="test-module", branch="main")
        db_session.add(source)
        await db_session.flush()

        cached = CachedModuleFile(
            source_id=source.id,
            file_type="workflow",
            file_path="workflows/db-workflow@1.0.0.yaml",
            content=DB_WORKFLOW_YAML,
            sha="abc123",
        )
        db_session.add(cached)
        await db_session.commit()

        # Create filesystem workflow with SAME ID
        wf_dir = os.path.join(tmpdir, "workflows")
        os.makedirs(wf_dir)
        with open(os.path.join(wf_dir, "db-workflow@1.0.0.yaml"), "w") as f:
            yaml.dump(OVERRIDE_WORKFLOW_YAML, f)

        mcp = make_mock_mcp()
        with (
            patch("src.shared.config.VELA_MODULES_DIR", os.path.join(tmpdir, "modules")),
            patch("src.mcp.modules.workflow_module.VELA_WORKFLOWS_DIR", wf_dir),
        ):
            module = WorkflowModule(mcp=mcp, session_factory=factory, module_registry=registry)

            wf = await module._get_workflow_async("db-workflow")
            assert wf is not None
            # Filesystem should win
            assert wf.name == "Overridden DB Workflow"

    async def test_list_workflows_includes_db_workflows(self, db_session, registry, tmpdir):
        """vela_list_workflows should include DB-stored workflows."""
        factory = _make_session_factory(db_session)
        registry._session_factory = factory

        # Insert DB workflow
        source = ModuleSource(provider="db", owner="db", name="test-module", branch="main")
        db_session.add(source)
        await db_session.flush()

        cached = CachedModuleFile(
            source_id=source.id,
            file_type="workflow",
            file_path="workflows/db-workflow@1.0.0.yaml",
            content=DB_WORKFLOW_YAML,
            sha="abc123",
        )
        db_session.add(cached)
        await db_session.commit()

        mcp = make_mock_mcp()
        with (
            patch("src.shared.config.VELA_MODULES_DIR", os.path.join(tmpdir, "modules")),
            patch("src.mcp.modules.workflow_module.VELA_WORKFLOWS_DIR", os.path.join(tmpdir, "workflows")),
        ):
            module = WorkflowModule(mcp=mcp, session_factory=factory, module_registry=registry)

            filtered = await module._get_filtered_workflows()
            assert "db-workflow@1.0.0" in filtered

    async def test_no_registry_falls_back_to_filesystem_only(self, tmpdir):
        """Without module_registry, only filesystem workflows are available."""
        wf_dir = os.path.join(tmpdir, "workflows")
        os.makedirs(wf_dir)
        with open(os.path.join(wf_dir, "fs-workflow@1.0.0.yaml"), "w") as f:
            yaml.dump(FILESYSTEM_WORKFLOW_YAML, f)

        mcp = make_mock_mcp()
        with (
            patch("src.shared.config.VELA_MODULES_DIR", os.path.join(tmpdir, "modules")),
            patch("src.mcp.modules.workflow_module.VELA_WORKFLOWS_DIR", wf_dir),
        ):
            module = WorkflowModule(mcp=mcp, module_registry=None)

            all_wfs = await module._get_all_workflows()
            assert "fs-workflow@1.0.0" in all_wfs
            assert len(all_wfs) == 1


# ---------------------------------------------------------------------------
# Agent YAML fixtures
# ---------------------------------------------------------------------------

DB_AGENT_YAML = """\
id: db-agent
name: DB Agent
persona: An agent stored in the database.
greeting: Hello from DB!
workflows:
  - db-workflow
tools:
  - vela_remember
"""

FILESYSTEM_AGENT_YAML = {
    "id": "fs-agent",
    "name": "Filesystem Agent",
    "persona": "An agent from the filesystem.",
    "greeting": "Hello from filesystem!",
    "workflows": ["fs-workflow"],
    "tools": ["vela_remember"],
}


class TestAgentModuleRegistryIntegration:
    """Verify AgentModule discovers agents from DB via ModuleRegistryService."""

    async def test_db_agent_found_via_get_all_agents(self, db_session, registry, tmpdir):
        """An agent pushed to DB should be found by _get_all_agents."""
        factory = _make_session_factory(db_session)
        registry._session_factory = factory

        source = ModuleSource(provider="db", owner="db", name="test-module", branch="main")
        db_session.add(source)
        await db_session.flush()

        cached = CachedModuleFile(
            source_id=source.id,
            file_type="agent",
            file_path="agents/db-agent.yaml",
            content=DB_AGENT_YAML,
            sha="abc123",
        )
        db_session.add(cached)
        await db_session.commit()

        mcp = make_mock_mcp()
        with (
            patch("src.shared.config.VELA_MODULES_DIR", os.path.join(tmpdir, "modules")),
            patch("src.mcp.modules.agent_module.VELA_AGENTS_DIR", os.path.join(tmpdir, "agents")),
        ):
            module = AgentModule(mcp=mcp, module_registry=registry)

            # Filesystem dict should NOT find it
            assert "db-agent" not in module._filesystem_agents

            # Async should find it
            all_agents = await module._get_all_agents()
            assert "db-agent" in all_agents
            assert all_agents["db-agent"].name == "DB Agent"

    async def test_agent_merge_and_override(self, db_session, registry, tmpdir):
        """Filesystem agent with same ID overrides DB agent."""
        factory = _make_session_factory(db_session)
        registry._session_factory = factory

        source = ModuleSource(provider="db", owner="db", name="test-module", branch="main")
        db_session.add(source)
        await db_session.flush()

        cached = CachedModuleFile(
            source_id=source.id,
            file_type="agent",
            file_path="agents/db-agent.yaml",
            content=DB_AGENT_YAML,
            sha="abc123",
        )
        db_session.add(cached)
        await db_session.commit()

        # Filesystem agent with same ID
        agent_dir = os.path.join(tmpdir, "agents")
        os.makedirs(agent_dir)
        override = {
            "id": "db-agent",
            "name": "Overridden Agent",
            "persona": "Override.",
        }
        with open(os.path.join(agent_dir, "db-agent.yaml"), "w") as f:
            yaml.dump(override, f)

        mcp = make_mock_mcp()
        with (
            patch("src.shared.config.VELA_MODULES_DIR", os.path.join(tmpdir, "modules")),
            patch("src.mcp.modules.agent_module.VELA_AGENTS_DIR", agent_dir),
        ):
            module = AgentModule(mcp=mcp, module_registry=registry)

            all_agents = await module._get_all_agents()
            assert all_agents["db-agent"].name == "Overridden Agent"

    async def test_list_agents_includes_db_agents(self, db_session, registry, tmpdir):
        """_get_filtered_agents should include DB-stored agents."""
        factory = _make_session_factory(db_session)
        registry._session_factory = factory

        source = ModuleSource(provider="db", owner="db", name="test-module", branch="main")
        db_session.add(source)
        await db_session.flush()

        cached = CachedModuleFile(
            source_id=source.id,
            file_type="agent",
            file_path="agents/db-agent.yaml",
            content=DB_AGENT_YAML,
            sha="abc123",
        )
        db_session.add(cached)
        await db_session.commit()

        mcp = make_mock_mcp()
        with (
            patch("src.shared.config.VELA_MODULES_DIR", os.path.join(tmpdir, "modules")),
            patch("src.mcp.modules.agent_module.VELA_AGENTS_DIR", os.path.join(tmpdir, "agents")),
        ):
            module = AgentModule(mcp=mcp, module_registry=registry)

            filtered = await module._get_filtered_agents()
            assert "db-agent" in filtered


# ---------------------------------------------------------------------------
# Resource YAML fixtures
# ---------------------------------------------------------------------------

DB_RESOURCE_YAML = """\
id: db-resource
name: DB Resource
type: schema
description: A resource stored in the database
content: "openapi: 3.0.0"
"""

FILESYSTEM_RESOURCE_YAML = {
    "id": "fs-resource",
    "name": "Filesystem Resource",
    "type": "schema",
    "description": "A resource from the filesystem",
    "content": "openapi: 3.0.0",
}


class TestResourceModuleRegistryIntegration:
    """Verify ResourceModule discovers resources from DB via ModuleRegistryService."""

    async def test_db_resource_found_via_get_all_resources(self, db_session, registry, tmpdir):
        """A resource pushed to DB should be found by _get_all_resources."""
        factory = _make_session_factory(db_session)
        registry._session_factory = factory

        source = ModuleSource(provider="db", owner="db", name="test-module", branch="main")
        db_session.add(source)
        await db_session.flush()

        cached = CachedModuleFile(
            source_id=source.id,
            file_type="resource",
            file_path="resources/db-resource.yaml",
            content=DB_RESOURCE_YAML,
            sha="abc123",
        )
        db_session.add(cached)
        await db_session.commit()

        mcp = make_mock_mcp()
        with (
            patch("src.shared.config.VELA_MODULES_DIR", os.path.join(tmpdir, "modules")),
            patch("src.mcp.modules.resource_module.VELA_RESOURCES_DIR", os.path.join(tmpdir, "resources")),
        ):
            module = ResourceModule(mcp=mcp, module_registry=registry)

            # Sync resolve should NOT find it
            assert module.resolve("db-resource") is None

            # Async should find it
            all_resources = await module._get_all_resources()
            assert "db-resource" in all_resources
            assert all_resources["db-resource"].name == "DB Resource"

    async def test_resource_resolve_async_finds_db_resource(self, db_session, registry, tmpdir):
        """resolve_async should find DB-stored resources."""
        factory = _make_session_factory(db_session)
        registry._session_factory = factory

        source = ModuleSource(provider="db", owner="db", name="test-module", branch="main")
        db_session.add(source)
        await db_session.flush()

        cached = CachedModuleFile(
            source_id=source.id,
            file_type="resource",
            file_path="resources/db-resource.yaml",
            content=DB_RESOURCE_YAML,
            sha="abc123",
        )
        db_session.add(cached)
        await db_session.commit()

        mcp = make_mock_mcp()
        with (
            patch("src.shared.config.VELA_MODULES_DIR", os.path.join(tmpdir, "modules")),
            patch("src.mcp.modules.resource_module.VELA_RESOURCES_DIR", os.path.join(tmpdir, "resources")),
        ):
            module = ResourceModule(mcp=mcp, module_registry=registry)

            resource = await module.resolve_async("db-resource")
            assert resource is not None
            assert resource.name == "DB Resource"

    async def test_resource_filter_includes_db_resources(self, db_session, registry, tmpdir):
        """_get_filtered_resources should include DB-stored resources."""
        factory = _make_session_factory(db_session)
        registry._session_factory = factory

        source = ModuleSource(provider="db", owner="db", name="test-module", branch="main")
        db_session.add(source)
        await db_session.flush()

        cached = CachedModuleFile(
            source_id=source.id,
            file_type="resource",
            file_path="resources/db-resource.yaml",
            content=DB_RESOURCE_YAML,
            sha="abc123",
        )
        db_session.add(cached)
        await db_session.commit()

        mcp = make_mock_mcp()
        with (
            patch("src.shared.config.VELA_MODULES_DIR", os.path.join(tmpdir, "modules")),
            patch("src.mcp.modules.resource_module.VELA_RESOURCES_DIR", os.path.join(tmpdir, "resources")),
        ):
            module = ResourceModule(mcp=mcp, module_registry=registry)

            filtered = await module._get_filtered_resources()
            assert "db-resource" in filtered

    async def test_filesystem_overrides_db_resource(self, db_session, registry, tmpdir):
        """Filesystem resource with same ID should override DB resource."""
        factory = _make_session_factory(db_session)
        registry._session_factory = factory

        source = ModuleSource(provider="db", owner="db", name="test-module", branch="main")
        db_session.add(source)
        await db_session.flush()

        cached = CachedModuleFile(
            source_id=source.id,
            file_type="resource",
            file_path="resources/db-resource.yaml",
            content=DB_RESOURCE_YAML,
            sha="abc123",
        )
        db_session.add(cached)
        await db_session.commit()

        res_dir = os.path.join(tmpdir, "resources")
        os.makedirs(res_dir)
        override = {
            "id": "db-resource",
            "name": "Overridden Resource",
            "type": "schema",
            "description": "Override",
            "content": "overridden",
        }
        with open(os.path.join(res_dir, "db-resource.yaml"), "w") as f:
            yaml.dump(override, f)

        mcp = make_mock_mcp()
        with (
            patch("src.shared.config.VELA_MODULES_DIR", os.path.join(tmpdir, "modules")),
            patch("src.mcp.modules.resource_module.VELA_RESOURCES_DIR", res_dir),
        ):
            module = ResourceModule(mcp=mcp, module_registry=registry)

            all_resources = await module._get_all_resources()
            assert all_resources["db-resource"].name == "Overridden Resource"
