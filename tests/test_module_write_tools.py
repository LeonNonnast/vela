"""Tests for Module Hub write tools: vela_create_module, vela_push_to_module, vela_delete_from_module."""

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.shared.db.models import CachedModuleFile, ModuleSource
from src.mcp.modules.module_hub_module import ModuleHubModule, parse_repo_string
from src.shared.services.github_api_service import GitHubApiService
from src.shared.services.module_registry_service import ModuleRegistryService


TOKEN = "ghp_test_token"


def _make_session_factory(db_session):
    @asynccontextmanager
    async def _factory():
        yield db_session
    return _factory


def _mock_ctx():
    """Create a mock Context."""
    ctx = AsyncMock()
    return ctx


class TestVelaCreateModule:
    async def test_create_module_success(self, db_session):
        factory = _make_session_factory(db_session)

        github = AsyncMock(spec=GitHubApiService)
        github.create_repo = AsyncMock(return_value={
            "owner": "testuser",
            "name": "my-module",
            "full_name": "testuser/my-module",
            "description": "Test module",
            "private": True,
            "default_branch": "main",
            "html_url": "https://github.com/testuser/my-module",
        })
        github.create_or_update_file = AsyncMock(return_value={
            "path": "vela.yaml",
            "sha": "manifestsha",
            "commit_sha": "commitsha",
        })
        github.get_manifest = AsyncMock(return_value=None)
        github.fetch_module_files = AsyncMock(return_value=[])

        registry = ModuleRegistryService(session_factory=factory, github=github)

        mcp = MagicMock()
        mcp.tool = MagicMock(return_value=lambda f: f)
        mcp.prompt = MagicMock(return_value=lambda f: f)

        module = ModuleHubModule.__new__(ModuleHubModule)
        module._mcp = mcp
        module._registry = registry
        module._github = github
        module._register_user_prompts = AsyncMock()

        ctx = _mock_ctx()

        with (
            patch("src.mcp.modules.module_hub_module._require_github_token", return_value=TOKEN),
        ):
            result_str = await ModuleHubModule._create_module_impl(
                module, "my-module", "Test module", True, "github", ctx,
            )

        result = json.loads(result_str)
        assert result["created"] is True
        assert result["repo"] == "testuser/my-module"
        assert "html_url" in result

    async def test_create_module_github_error(self, db_session):
        github = AsyncMock(spec=GitHubApiService)
        github.create_repo = AsyncMock(return_value={"error": "Repository name already exists or is invalid"})

        module = ModuleHubModule.__new__(ModuleHubModule)
        module._mcp = MagicMock()
        module._github = github

        ctx = _mock_ctx()

        with patch("src.mcp.modules.module_hub_module._require_github_token", return_value=TOKEN):
            result_str = await ModuleHubModule._create_module_impl(module, "existing", "", True, "github", ctx)

        result = json.loads(result_str)
        assert "error" in result


class TestVelaPushToModule:
    async def test_push_new_workflow(self, db_session):
        factory = _make_session_factory(db_session)

        # Create module source in DB
        source = ModuleSource(
            provider="github", owner="testuser", name="my-module", branch="main",
        )
        db_session.add(source)
        await db_session.commit()
        await db_session.refresh(source)

        github = AsyncMock(spec=GitHubApiService)
        github.get_file_content = AsyncMock(return_value=None)  # File doesn't exist
        github.create_or_update_file = AsyncMock(return_value={
            "path": "workflows/my-wf@1.0.0.yaml",
            "sha": "newsha",
            "commit_sha": "commitsha",
        })

        registry = ModuleRegistryService(session_factory=factory, github=github)

        module = ModuleHubModule.__new__(ModuleHubModule)
        module._mcp = MagicMock()
        module._registry = registry
        module._github = github
        module._register_user_prompts = AsyncMock()

        ctx = _mock_ctx()
        content = "id: my-wf\nname: My Workflow\nversion: '1.0.0'\nsteps:\n  - id: s1\n    type: freeform\n    prompt: Hello\n"

        with (
            patch("src.mcp.modules.module_hub_module._require_github_token", return_value=TOKEN),
        ):
            result_str = await ModuleHubModule._push_to_module_impl(
                module, "testuser/my-module", "workflow", content, None, None, ctx,
            )

        result = json.loads(result_str)
        assert result["pushed"] is True
        assert result["action"] == "created"
        assert result["path"] == "workflows/my-wf@1.0.0.yaml"

    async def test_push_update_existing(self, db_session):
        factory = _make_session_factory(db_session)

        source = ModuleSource(
            provider="github", owner="testuser", name="my-module", branch="main",
        )
        db_session.add(source)
        await db_session.commit()

        github = AsyncMock(spec=GitHubApiService)
        github.get_file_content = AsyncMock(return_value=("old content", "oldsha123"))
        github.create_or_update_file = AsyncMock(return_value={
            "path": "agents/helper.yaml",
            "sha": "updatedsha",
            "commit_sha": "commitsha",
        })

        registry = ModuleRegistryService(session_factory=factory, github=github)

        module = ModuleHubModule.__new__(ModuleHubModule)
        module._mcp = MagicMock()
        module._registry = registry
        module._github = github
        module._register_user_prompts = AsyncMock()

        ctx = _mock_ctx()
        content = "id: helper\nname: Helper Agent\npersona: You help.\n"

        with (
            patch("src.mcp.modules.module_hub_module._require_github_token", return_value=TOKEN),
        ):
            result_str = await ModuleHubModule._push_to_module_impl(
                module, "testuser/my-module", "agent", content, None, None, ctx,
            )

        result = json.loads(result_str)
        assert result["pushed"] is True
        assert result["action"] == "updated"

        # Verify sha was passed for update
        github.create_or_update_file.assert_called_once()
        call_kwargs = github.create_or_update_file.call_args
        assert call_kwargs[0][6] == "oldsha123" or call_kwargs.kwargs.get("sha") == "oldsha123"

    async def test_push_auto_filename_workflow(self, db_session):
        factory = _make_session_factory(db_session)

        source = ModuleSource(
            provider="github", owner="o", name="r", branch="main",
        )
        db_session.add(source)
        await db_session.commit()

        github = AsyncMock(spec=GitHubApiService)
        github.get_file_content = AsyncMock(return_value=None)
        github.create_or_update_file = AsyncMock(return_value={
            "path": "workflows/planning@2.0.0.yaml",
            "sha": "sha1",
            "commit_sha": "c1",
        })

        registry = ModuleRegistryService(session_factory=factory, github=github)

        module = ModuleHubModule.__new__(ModuleHubModule)
        module._mcp = MagicMock()
        module._registry = registry
        module._github = github
        module._register_user_prompts = AsyncMock()

        ctx = _mock_ctx()
        content = "id: planning\nname: Planning\nversion: '2.0.0'\nsteps: []\n"

        with (
            patch("src.mcp.modules.module_hub_module._require_github_token", return_value=TOKEN),
        ):
            result_str = await ModuleHubModule._push_to_module_impl(
                module, "o/r", "workflow", content, None, None, ctx,
            )

        result = json.loads(result_str)
        assert result["path"] == "workflows/planning@2.0.0.yaml"

    async def test_push_auto_filename_agent(self, db_session):
        factory = _make_session_factory(db_session)

        source = ModuleSource(
            provider="github", owner="o", name="r", branch="main",
        )
        db_session.add(source)
        await db_session.commit()

        github = AsyncMock(spec=GitHubApiService)
        github.get_file_content = AsyncMock(return_value=None)
        github.create_or_update_file = AsyncMock(return_value={
            "path": "agents/reviewer.yaml",
            "sha": "sha1",
            "commit_sha": "c1",
        })

        registry = ModuleRegistryService(session_factory=factory, github=github)

        module = ModuleHubModule.__new__(ModuleHubModule)
        module._mcp = MagicMock()
        module._registry = registry
        module._github = github
        module._register_user_prompts = AsyncMock()

        ctx = _mock_ctx()
        content = "id: reviewer\nname: Code Reviewer\npersona: Review code.\n"

        with (
            patch("src.mcp.modules.module_hub_module._require_github_token", return_value=TOKEN),
        ):
            result_str = await ModuleHubModule._push_to_module_impl(
                module, "o/r", "agent", content, None, None, ctx,
            )

        result = json.loads(result_str)
        assert result["path"] == "agents/reviewer.yaml"

    async def test_push_invalid_file_type(self, db_session):
        module = ModuleHubModule.__new__(ModuleHubModule)
        module._mcp = MagicMock()
        module._github = AsyncMock()

        ctx = _mock_ctx()

        with patch("src.mcp.modules.module_hub_module._require_github_token", return_value=TOKEN):
            result_str = await ModuleHubModule._push_to_module_impl(
                module, "o/r", "unknown", "content", None, None, ctx,
            )

        result = json.loads(result_str)
        assert "error" in result
        assert "unknown" in result["error"]


class TestVelaDeleteFromModule:
    async def test_delete_success(self, db_session):
        factory = _make_session_factory(db_session)

        source = ModuleSource(
            provider="github", owner="testuser", name="my-module", branch="main",
        )
        db_session.add(source)
        await db_session.commit()

        github = AsyncMock(spec=GitHubApiService)
        github.get_file_content = AsyncMock(return_value=("content", "filesha"))
        github.delete_file = AsyncMock(return_value={
            "path": "workflows/old@1.0.0.yaml",
            "deleted": True,
            "commit_sha": "delcommit",
        })

        registry = ModuleRegistryService(session_factory=factory, github=github)

        module = ModuleHubModule.__new__(ModuleHubModule)
        module._mcp = MagicMock()
        module._registry = registry
        module._github = github
        module._register_user_prompts = AsyncMock()

        ctx = _mock_ctx()

        with (
            patch("src.mcp.modules.module_hub_module._require_github_token", return_value=TOKEN),
        ):
            result_str = await ModuleHubModule._delete_from_module_impl(
                module, "testuser/my-module", "workflows/old@1.0.0.yaml", ctx,
            )

        result = json.loads(result_str)
        assert result["deleted"] is True
        assert result["repo"] == "testuser/my-module"

    async def test_delete_not_found(self, db_session):
        factory = _make_session_factory(db_session)
        github = AsyncMock(spec=GitHubApiService)
        github.get_file_content = AsyncMock(return_value=None)

        registry = ModuleRegistryService(session_factory=factory, github=github)

        module = ModuleHubModule.__new__(ModuleHubModule)
        module._mcp = MagicMock()
        module._registry = registry
        module._github = github
        ctx = _mock_ctx()

        with (
            patch("src.mcp.modules.module_hub_module._require_github_token", return_value=TOKEN),
        ):
            result_str = await ModuleHubModule._delete_from_module_impl(
                module, "testuser/my-module", "missing.yaml", ctx,
            )

        result = json.loads(result_str)
        assert "error" in result
        assert "not found" in result["error"].lower()
