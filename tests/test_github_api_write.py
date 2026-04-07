"""Tests for GitHubApiService write methods (create_repo, create_or_update_file, delete_file)."""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.shared.services.github_api_service import GitHubApiService


def _mock_response(status_code: int = 200, json_data=None):
    """Create a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=MagicMock(),
            response=resp,
        )
    return resp


def _mock_client(responses: list, method: str = "get"):
    """Create a mock AsyncClient that returns responses in order."""
    client = AsyncMock()
    setattr(client, method, AsyncMock(side_effect=responses))
    # Also mock request() for DELETE
    client.request = AsyncMock(side_effect=responses)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx, client


TOKEN = "ghp_test_token_12345"


class TestCreateRepo:
    async def test_create_repo_success(self):
        api_data = {
            "owner": {"login": "testuser"},
            "name": "my-module",
            "full_name": "testuser/my-module",
            "description": "A test module",
            "private": True,
            "default_branch": "main",
            "html_url": "https://github.com/testuser/my-module",
        }
        resp = _mock_response(201, api_data)
        ctx, client = _mock_client([resp], "post")

        svc = GitHubApiService()
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await svc.create_repo(TOKEN, "my-module", "A test module", True)

        assert result["owner"] == "testuser"
        assert result["name"] == "my-module"
        assert result["html_url"] == "https://github.com/testuser/my-module"
        assert result["private"] is True
        assert "error" not in result

    async def test_create_repo_conflict_422(self):
        resp = _mock_response(422)
        ctx, client = _mock_client([resp], "post")

        svc = GitHubApiService()
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await svc.create_repo(TOKEN, "existing-repo")

        assert "error" in result
        assert "already exists" in result["error"]

    async def test_create_repo_with_description(self):
        api_data = {
            "owner": {"login": "testuser"},
            "name": "my-module",
            "full_name": "testuser/my-module",
            "description": "Custom description",
            "private": False,
            "default_branch": "main",
            "html_url": "https://github.com/testuser/my-module",
        }
        resp = _mock_response(201, api_data)
        ctx, client = _mock_client([resp], "post")

        svc = GitHubApiService()
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await svc.create_repo(TOKEN, "my-module", "Custom description", False)

        assert result["description"] == "Custom description"
        assert result["private"] is False

        # Verify the request body included description
        call_kwargs = client.post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["description"] == "Custom description"
        assert body["auto_init"] is True


class TestCreateOrUpdateFile:
    async def test_create_new_file(self):
        api_data = {
            "content": {"path": "workflows/test@1.0.0.yaml", "sha": "newsha123"},
            "commit": {"sha": "commitsha456"},
        }
        resp = _mock_response(201, api_data)
        ctx, client = _mock_client([resp], "put")

        svc = GitHubApiService()
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await svc.create_or_update_file(
                TOKEN, "owner", "repo", "workflows/test@1.0.0.yaml",
                "id: test\nname: Test", "Add workflow test",
            )

        assert result["path"] == "workflows/test@1.0.0.yaml"
        assert result["sha"] == "newsha123"
        assert result["commit_sha"] == "commitsha456"

        # Verify no sha in request body (create, not update)
        call_kwargs = client.put.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "sha" not in body

    async def test_update_existing_file(self):
        api_data = {
            "content": {"path": "workflows/test@1.0.0.yaml", "sha": "updatedsha"},
            "commit": {"sha": "commitsha789"},
        }
        resp = _mock_response(200, api_data)
        ctx, client = _mock_client([resp], "put")

        svc = GitHubApiService()
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await svc.create_or_update_file(
                TOKEN, "owner", "repo", "workflows/test@1.0.0.yaml",
                "id: test\nname: Test Updated", "Update workflow test",
                sha="oldsha123",
            )

        assert result["sha"] == "updatedsha"

        # Verify sha is in request body (update)
        call_kwargs = client.put.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["sha"] == "oldsha123"

    async def test_update_sha_conflict_409(self):
        resp = _mock_response(409)
        ctx, client = _mock_client([resp], "put")

        svc = GitHubApiService()
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await svc.create_or_update_file(
                TOKEN, "owner", "repo", "file.yaml",
                "content", "msg", sha="stalesha",
            )

        assert "error" in result
        assert "SHA conflict" in result["error"]

    async def test_content_base64_encoded(self):
        api_data = {
            "content": {"path": "test.yaml", "sha": "sha1"},
            "commit": {"sha": "c1"},
        }
        resp = _mock_response(201, api_data)
        ctx, client = _mock_client([resp], "put")

        content = "id: test\nname: Test Workflow\nversion: 1.0.0"
        expected_b64 = base64.b64encode(content.encode()).decode()

        svc = GitHubApiService()
        with patch("httpx.AsyncClient", return_value=ctx):
            await svc.create_or_update_file(
                TOKEN, "owner", "repo", "test.yaml", content, "msg",
            )

        call_kwargs = client.put.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["content"] == expected_b64


class TestDeleteFile:
    async def test_delete_file_success(self):
        api_data = {
            "commit": {"sha": "deletecommit123"},
        }
        resp = _mock_response(200, api_data)
        ctx, client = _mock_client([resp])

        svc = GitHubApiService()
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await svc.delete_file(
                TOKEN, "owner", "repo", "workflows/old.yaml",
                "filesha123", "Delete old.yaml",
            )

        assert result["deleted"] is True
        assert result["path"] == "workflows/old.yaml"
        assert result["commit_sha"] == "deletecommit123"

        # Verify sha in request body
        call_kwargs = client.request.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["sha"] == "filesha123"

    async def test_delete_file_not_found_404(self):
        resp = _mock_response(404)
        ctx, client = _mock_client([resp])

        svc = GitHubApiService()
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await svc.delete_file(
                TOKEN, "owner", "repo", "missing.yaml",
                "sha123", "Delete missing",
            )

        assert "error" in result
        assert "not found" in result["error"].lower()
