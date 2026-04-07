"""Tests for GitHubApiService with mocked HTTP responses."""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.shared.services.github_api_service import GitHubApiService, ModuleFileInfo


def _mock_response(status_code: int = 200, json_data=None):
    """Create a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


def _mock_client(responses: list):
    """Create a mock AsyncClient that returns responses in order.

    Each response is a mock httpx.Response. GET calls return them sequentially.
    """
    client = AsyncMock()
    client.get = AsyncMock(side_effect=responses)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx, client


TOKEN = "ghp_test_token_12345"


class TestListUserRepos:
    async def test_list_user_repos(self):
        api_response = [
            {
                "owner": {"login": "acme"},
                "name": "vela-modules",
                "full_name": "acme/vela-modules",
                "description": "Modules repo",
                "private": False,
                "stargazers_count": 5,
                "default_branch": "main",
                "html_url": "https://github.com/acme/vela-modules",
            }
        ]
        resp = _mock_response(200, api_response)
        ctx, client = _mock_client([resp])

        svc = GitHubApiService()
        with patch("httpx.AsyncClient", return_value=ctx):
            repos = await svc.list_user_repos(TOKEN)

        assert len(repos) == 1
        assert repos[0]["owner"] == "acme"
        assert repos[0]["name"] == "vela-modules"
        assert repos[0]["full_name"] == "acme/vela-modules"
        assert repos[0]["private"] is False


class TestGetRepoInfo:
    async def test_get_repo_info(self):
        api_data = {
            "owner": {"login": "acme"},
            "name": "modules",
            "full_name": "acme/modules",
            "description": "desc",
            "private": True,
            "default_branch": "develop",
        }
        resp = _mock_response(200, api_data)
        ctx, _ = _mock_client([resp])

        svc = GitHubApiService()
        with patch("httpx.AsyncClient", return_value=ctx):
            info = await svc.get_repo_info(TOKEN, "acme", "modules")

        assert info is not None
        assert info["owner"] == "acme"
        assert info["name"] == "modules"
        assert info["default_branch"] == "develop"

    async def test_get_repo_info_not_found(self):
        resp = _mock_response(404)
        # Override raise_for_status for 404 (we handle it before raise)
        resp.raise_for_status = MagicMock()
        ctx, _ = _mock_client([resp])

        svc = GitHubApiService()
        with patch("httpx.AsyncClient", return_value=ctx):
            info = await svc.get_repo_info(TOKEN, "acme", "nonexistent")

        assert info is None


class TestListDirectory:
    async def test_list_directory(self):
        entries = [
            {"name": "plan@1.0.0.yaml", "path": "workflows/plan@1.0.0.yaml",
             "sha": "aaa", "type": "file"},
            {"name": "sub", "path": "workflows/sub",
             "sha": "bbb", "type": "dir"},
        ]
        resp = _mock_response(200, entries)
        ctx, _ = _mock_client([resp])

        svc = GitHubApiService()
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await svc.list_directory(TOKEN, "acme", "repo", "workflows")

        assert len(result) == 2
        assert result[0]["name"] == "plan@1.0.0.yaml"
        assert result[0]["type"] == "file"

    async def test_list_directory_not_found(self):
        resp = _mock_response(404)
        resp.raise_for_status = MagicMock()
        ctx, _ = _mock_client([resp])

        svc = GitHubApiService()
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await svc.list_directory(TOKEN, "acme", "repo", "missing")

        assert result == []


class TestGetFileContent:
    async def test_get_file_content(self):
        raw = "id: test\nname: Test Workflow"
        encoded = base64.b64encode(raw.encode()).decode()
        api_data = {"type": "file", "content": encoded, "sha": "file-sha-1"}
        resp = _mock_response(200, api_data)
        ctx, _ = _mock_client([resp])

        svc = GitHubApiService()
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await svc.get_file_content(TOKEN, "acme", "repo", "workflows/test.yaml")

        assert result is not None
        content, sha = result
        assert content == raw
        assert sha == "file-sha-1"

    async def test_get_file_content_not_found(self):
        resp = _mock_response(404)
        resp.raise_for_status = MagicMock()
        ctx, _ = _mock_client([resp])

        svc = GitHubApiService()
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await svc.get_file_content(TOKEN, "acme", "repo", "missing.yaml")

        assert result is None


class TestFetchModuleFiles:
    async def test_fetch_module_files(self):
        """Test scanning workflows/, agents/, resources/ directories."""
        svc = GitHubApiService()

        workflow_yaml = "id: plan\nname: Plan\nsteps: []"
        agent_yaml = "id: helper\nname: Helper"

        # Mock list_directory and get_file_content
        async def mock_list_directory(token, owner, name, path, branch="main", **kwargs):
            if path == "workflows":
                return [
                    {"name": "plan@1.0.0.yaml", "path": "workflows/plan@1.0.0.yaml",
                     "sha": "d1", "type": "file"},
                ]
            elif path == "agents":
                return [
                    {"name": "helper.yaml", "path": "agents/helper.yaml",
                     "sha": "d2", "type": "file"},
                    {"name": "readme.md", "path": "agents/readme.md",
                     "sha": "d3", "type": "file"},
                ]
            elif path == "resources":
                return []
            return []

        async def mock_get_file_content(token, owner, name, path, branch="main", **kwargs):
            if path == "workflows/plan@1.0.0.yaml":
                return (workflow_yaml, "sha-wf")
            elif path == "agents/helper.yaml":
                return (agent_yaml, "sha-ag")
            return None

        svc.list_directory = mock_list_directory
        svc.get_file_content = mock_get_file_content

        files = await svc.fetch_module_files(TOKEN, "acme", "repo", "main")

        assert len(files) == 2

        wf_files = [f for f in files if f.file_type == "workflow"]
        assert len(wf_files) == 1
        assert wf_files[0].file_path == "workflows/plan@1.0.0.yaml"
        assert wf_files[0].content == workflow_yaml

        ag_files = [f for f in files if f.file_type == "agent"]
        assert len(ag_files) == 1
        assert ag_files[0].file_path == "agents/helper.yaml"
        # readme.md should be skipped (not .yaml/.yml)
