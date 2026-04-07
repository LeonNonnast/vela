"""Tests for ModuleRegistryService — integration-style with real DB, mocked GitHub API."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

from src.shared.db.models import CachedModuleFile, ModuleSource
from src.shared.services.github_api_service import ModuleFileInfo
from src.shared.services.module_registry_service import ModuleRegistryService, UserModules


TOKEN = "ghp_test_token"

WORKFLOW_YAML = """\
id: feature-planning
version: "1.0.0"
name: Feature Planning
description: Plan a new feature
steps:
  - id: step-1
    type: freeform
    prompt: Describe the feature
"""

AGENT_YAML = """\
id: architect
name: Software Architect
persona: You are a senior software architect.
greeting: What shall we build?
workflows:
  - feature-planning
tools:
  - vela_remember
"""

RESOURCE_YAML = """\
id: api-schema
name: API Schema
type: schema
description: OpenAPI schema
content: "openapi: 3.0.0"
"""


@pytest.fixture
def mock_github():
    """Fixture that patches GitHubApiService methods on the registry's .github attribute."""
    github = AsyncMock()
    github.get_manifest = AsyncMock(return_value=None)
    github.fetch_module_files = AsyncMock(return_value=[
        ModuleFileInfo(
            file_type="workflow",
            file_path="workflows/feature-planning@1.0.0.yaml",
            content=WORKFLOW_YAML,
            sha="sha-wf",
        ),
        ModuleFileInfo(
            file_type="agent",
            file_path="agents/architect.yaml",
            content=AGENT_YAML,
            sha="sha-ag",
        ),
    ])
    return github


def _make_session_factory(db_session):
    """Create a callable that returns an async context manager wrapping db_session."""
    @asynccontextmanager
    async def _factory():
        yield db_session
    return _factory


@pytest.fixture
def registry(mock_github):
    """Create a fresh ModuleRegistryService with mocked GitHub."""
    svc = ModuleRegistryService(github=mock_github)
    return svc


class TestRegisterRepo:
    async def test_register_repo(self, db_session, registry, mock_github):
        """Register a new repo: should create DB entries and return stats."""
        registry._session_factory = _make_session_factory(db_session)
        result = await registry.register_repo(
            token=TOKEN,
            owner="acme",
            name="modules",
            branch="main",
        )

        assert result["registered"] is True
        assert result["repo"] == "acme/modules"
        assert result["stats"]["workflows"] == 1
        assert result["stats"]["agents"] == 1
        assert result["stats"]["resources"] == 0

    async def test_register_repo_already_registered(self, db_session, registry, mock_github):
        """Re-registering an existing repo triggers sync instead."""
        source = ModuleSource(
            provider="github",
            owner="acme",
            name="modules",
            branch="main",
        )
        db_session.add(source)
        await db_session.commit()
        await db_session.refresh(source)

        registry._session_factory = _make_session_factory(db_session)
        result = await registry.register_repo(
            token=TOKEN,
            owner="acme",
            name="modules",
        )

        assert result["synced"] is True
        assert result["repo"] == "acme/modules"


class TestUnregisterRepo:
    async def test_unregister_repo(self, db_session, registry):
        source = ModuleSource(
            provider="github",
            owner="acme",
            name="modules",
            branch="main",
        )
        db_session.add(source)
        await db_session.commit()
        await db_session.refresh(source)

        registry._session_factory = _make_session_factory(db_session)
        result = await registry.unregister_repo(
            owner="acme",
            name="modules",
        )

        assert result["unregistered"] is True
        assert result["repo"] == "acme/modules"

    async def test_unregister_repo_not_found(self, db_session, registry):
        registry._session_factory = _make_session_factory(db_session)
        result = await registry.unregister_repo(
            owner="ghost",
            name="nope",
        )

        assert "error" in result
        assert result["repo"] == "ghost/nope"


class TestSyncRepo:
    async def test_sync_repo(self, db_session, registry, mock_github):
        source = ModuleSource(
            provider="github",
            owner="acme",
            name="modules",
            branch="main",
        )
        db_session.add(source)
        await db_session.commit()
        await db_session.refresh(source)

        registry._session_factory = _make_session_factory(db_session)
        result = await registry.sync_repo(
            token=TOKEN,
            owner="acme",
            name="modules",
        )

        assert result["synced"] is True
        assert result["stats"]["workflows"] == 1
        assert result["stats"]["agents"] == 1


class TestLoadModules:
    async def test_load_modules(self, db_session, registry):
        """Load modules from DB cache into memory."""
        source = ModuleSource(
            provider="github",
            owner="acme",
            name="modules",
            branch="main",
            is_active=True,
        )
        db_session.add(source)
        await db_session.commit()
        await db_session.refresh(source)

        wf_file = CachedModuleFile(
            source_id=source.id,
            file_type="workflow",
            file_path="workflows/feature-planning@1.0.0.yaml",
            content=WORKFLOW_YAML,
            sha="sha1",
        )
        ag_file = CachedModuleFile(
            source_id=source.id,
            file_type="agent",
            file_path="agents/architect.yaml",
            content=AGENT_YAML,
            sha="sha2",
        )
        db_session.add_all([wf_file, ag_file])
        await db_session.commit()

        registry._session_factory = _make_session_factory(db_session)
        modules = await registry.load_modules()

        assert len(modules.workflows) == 1
        assert "feature-planning@1.0.0" in modules.workflows
        assert modules.workflows["feature-planning@1.0.0"].name == "Feature Planning"

        assert len(modules.agents) == 1
        assert "architect" in modules.agents
        assert modules.agents["architect"].name == "Software Architect"

    async def test_load_modules_caching(self, db_session, registry):
        """Second call returns the in-memory cached result without DB hit."""
        cached_modules = UserModules()
        registry._modules_cache = cached_modules

        modules = await registry.load_modules()
        assert modules is cached_modules


class TestParseFromCache:
    async def test_parse_workflow_from_cache(self, registry):
        """Parsing workflow YAML from a CachedModuleFile produces a WorkflowDefinition."""
        wf_file = CachedModuleFile(
            source_id="dummy",
            file_type="workflow",
            file_path="workflows/feature-planning@1.0.0.yaml",
            content=WORKFLOW_YAML,
            sha="sha-wf",
        )

        modules = UserModules()
        registry._parse_and_add(wf_file, modules)

        assert "feature-planning@1.0.0" in modules.workflows
        wf = modules.workflows["feature-planning@1.0.0"]
        assert wf.name == "Feature Planning"
        assert wf.description == "Plan a new feature"
        assert len(wf.steps) == 1

    async def test_parse_agent_from_cache(self, registry):
        """Parsing agent YAML from a CachedModuleFile produces an AgentDefinition."""
        ag_file = CachedModuleFile(
            source_id="dummy",
            file_type="agent",
            file_path="agents/architect.yaml",
            content=AGENT_YAML,
            sha="sha-ag",
        )

        modules = UserModules()
        registry._parse_and_add(ag_file, modules)

        assert "architect" in modules.agents
        agent = modules.agents["architect"]
        assert agent.name == "Software Architect"
        assert agent.persona == "You are a senior software architect."
        assert "feature-planning" in agent.workflows

    async def test_parse_resource_from_cache(self, registry):
        """Parsing resource YAML from a CachedModuleFile produces a ResourceDefinition."""
        res_file = CachedModuleFile(
            source_id="dummy",
            file_type="resource",
            file_path="resources/api-schema.yaml",
            content=RESOURCE_YAML,
            sha="sha-res",
        )

        modules = UserModules()
        registry._parse_and_add(res_file, modules)

        assert "api-schema" in modules.resources
        res = modules.resources["api-schema"]
        assert res.name == "API Schema"

    async def test_parse_invalid_yaml_skipped(self, registry):
        """Invalid YAML content is silently skipped."""
        bad_file = CachedModuleFile(
            source_id="dummy",
            file_type="workflow",
            file_path="workflows/broken.yaml",
            content="this: is: [not: valid yaml {{",
            sha="sha-bad",
        )

        modules = UserModules()
        registry._parse_and_add(bad_file, modules)
        assert len(modules.workflows) == 0


class TestListReposWithStats:
    async def test_list_repos_with_stats(self, db_session, registry):
        source = ModuleSource(
            provider="github",
            owner="acme",
            name="modules",
            branch="main",
            is_active=True,
        )
        db_session.add(source)
        await db_session.commit()
        await db_session.refresh(source)

        wf = CachedModuleFile(
            source_id=source.id,
            file_type="workflow",
            file_path="workflows/a.yaml",
            content="content",
            sha="s1",
        )
        ag = CachedModuleFile(
            source_id=source.id,
            file_type="agent",
            file_path="agents/b.yaml",
            content="content",
            sha="s2",
        )
        db_session.add_all([wf, ag])
        await db_session.commit()

        registry._session_factory = _make_session_factory(db_session)
        repos = await registry.list_repos()

        assert len(repos) == 1
        assert repos[0]["repo"] == "acme/modules"
        assert repos[0]["stats"]["workflows"] == 1
        assert repos[0]["stats"]["agents"] == 1
        assert repos[0]["stats"]["resources"] == 0


class TestUpdateCachedFile:
    async def test_upsert_new_file(self, db_session, registry):
        """Upserting a new file into cache creates a CachedModuleFile."""
        source = ModuleSource(
            provider="github",
            owner="acme",
            name="modules",
            branch="main",
        )
        db_session.add(source)
        await db_session.commit()
        await db_session.refresh(source)

        registry._session_factory = _make_session_factory(db_session)
        await registry.update_cached_file(
            owner="acme",
            name="modules",
            file_type="workflow",
            file_path="workflows/new@1.0.0.yaml",
            content="id: new\nname: New\nsteps: []",
            sha="newsha",
        )

        # Verify file was created
        from sqlalchemy import select
        result = await db_session.execute(
            select(CachedModuleFile).where(
                CachedModuleFile.source_id == source.id,
                CachedModuleFile.file_path == "workflows/new@1.0.0.yaml",
            )
        )
        cached = result.scalar_one_or_none()
        assert cached is not None
        assert cached.sha == "newsha"
        assert cached.file_type == "workflow"

    async def test_upsert_update_existing(self, db_session, registry):
        """Upserting an existing file updates its content and sha."""
        source = ModuleSource(
            provider="github",
            owner="acme",
            name="modules",
            branch="main",
        )
        db_session.add(source)
        await db_session.commit()
        await db_session.refresh(source)

        existing = CachedModuleFile(
            source_id=source.id,
            file_type="workflow",
            file_path="workflows/test@1.0.0.yaml",
            content="old content",
            sha="oldsha",
        )
        db_session.add(existing)
        await db_session.commit()

        registry._session_factory = _make_session_factory(db_session)
        await registry.update_cached_file(
            owner="acme",
            name="modules",
            file_type="workflow",
            file_path="workflows/test@1.0.0.yaml",
            content="new content",
            sha="newsha",
        )

        await db_session.refresh(existing)
        assert existing.content == "new content"
        assert existing.sha == "newsha"

    async def test_source_not_found(self, db_session, registry):
        """Upserting a file for nonexistent source is a no-op."""
        registry._session_factory = _make_session_factory(db_session)
        # Should not raise
        await registry.update_cached_file(
            owner="ghost",
            name="nope",
            file_type="workflow",
            file_path="workflows/x.yaml",
            content="content",
            sha="sha",
        )


class TestDeleteCachedFile:
    async def test_delete_existing_file(self, db_session, registry):
        """Deleting an existing cached file removes it from DB."""
        source = ModuleSource(
            provider="github",
            owner="acme",
            name="modules",
            branch="main",
        )
        db_session.add(source)
        await db_session.commit()
        await db_session.refresh(source)

        cached = CachedModuleFile(
            source_id=source.id,
            file_type="agent",
            file_path="agents/helper.yaml",
            content="id: helper\nname: Helper",
            sha="sha1",
        )
        db_session.add(cached)
        await db_session.commit()

        registry._session_factory = _make_session_factory(db_session)
        await registry.delete_cached_file(
            owner="acme",
            name="modules",
            file_path="agents/helper.yaml",
        )

        from sqlalchemy import select
        result = await db_session.execute(
            select(CachedModuleFile).where(
                CachedModuleFile.source_id == source.id,
                CachedModuleFile.file_path == "agents/helper.yaml",
            )
        )
        assert result.scalar_one_or_none() is None

    async def test_delete_nonexistent_file(self, db_session, registry):
        """Deleting a nonexistent file is a graceful no-op."""
        source = ModuleSource(
            provider="github",
            owner="acme",
            name="modules",
            branch="main",
        )
        db_session.add(source)
        await db_session.commit()

        registry._session_factory = _make_session_factory(db_session)
        # Should not raise
        await registry.delete_cached_file(
            owner="acme",
            name="modules",
            file_path="agents/nonexistent.yaml",
        )
