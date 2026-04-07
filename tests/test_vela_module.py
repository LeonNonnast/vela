"""Tests for AdminModule (formerly VelaModule) — validate, save, status, and prompts."""

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from tests.conftest import make_mock_mcp, reset_singleton


class TestVelaValidate:
    """Tests for vela_validate tool."""

    def _make_module(self):
        from src.mcp.modules.vela_module import AdminModule
        reset_singleton(AdminModule)
        mock_mcp = make_mock_mcp()
        # Add prompt capture
        mock_mcp._prompts = {}
        def capture_prompt(name: str, description: str = ""):
            def decorator(func):
                mock_mcp._prompts[name] = {"handler": func, "description": description}
                return func
            return decorator
        mock_mcp.prompt = capture_prompt
        AdminModule.construct(mcp=mock_mcp)
        return mock_mcp

    async def test_validate_valid_agent(self):
        mock_mcp = self._make_module()
        handler = mock_mcp._tools["vela_validate"]["handler"]
        content = yaml.dump({"id": "test", "name": "Test Agent", "persona": "hello"})
        result = json.loads(await handler(type="agent", content=content))
        assert result["valid"] is True

    async def test_validate_valid_workflow(self):
        mock_mcp = self._make_module()
        handler = mock_mcp._tools["vela_validate"]["handler"]
        content = yaml.dump({
            "id": "test",
            "name": "Test WF",
            "steps": [{"id": "s1", "type": "freeform", "prompt": "go"}],
        })
        result = json.loads(await handler(type="workflow", content=content))
        assert result["valid"] is True

    async def test_validate_valid_resource(self):
        mock_mcp = self._make_module()
        handler = mock_mcp._tools["vela_validate"]["handler"]
        content = yaml.dump({
            "id": "test",
            "name": "Test Resource",
            "type": "schema",
            "content": "hello world",
        })
        result = json.loads(await handler(type="resource", content=content))
        assert result["valid"] is True

    async def test_validate_invalid_agent_missing_name(self):
        mock_mcp = self._make_module()
        handler = mock_mcp._tools["vela_validate"]["handler"]
        content = yaml.dump({"id": "test"})
        result = json.loads(await handler(type="agent", content=content))
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    async def test_validate_bad_yaml_syntax(self):
        mock_mcp = self._make_module()
        handler = mock_mcp._tools["vela_validate"]["handler"]
        result = json.loads(await handler(type="agent", content=": bad: yaml: ["))
        assert result["valid"] is False
        assert "syntax" in result["errors"][0].lower() or "YAML" in result["errors"][0]

    async def test_validate_unknown_type(self):
        mock_mcp = self._make_module()
        handler = mock_mcp._tools["vela_validate"]["handler"]
        result = json.loads(await handler(type="unknown", content="id: x"))
        assert result["valid"] is False
        assert "Unknown type" in result["errors"][0]

    async def test_validate_empty_content(self):
        mock_mcp = self._make_module()
        handler = mock_mcp._tools["vela_validate"]["handler"]
        result = json.loads(await handler(type="agent", content=""))
        assert result["valid"] is False


class TestVelaSave:
    """Tests for vela_save tool."""

    def _make_module(self):
        from src.mcp.modules.vela_module import AdminModule
        reset_singleton(AdminModule)
        mock_mcp = make_mock_mcp()
        mock_mcp._prompts = {}
        def capture_prompt(name: str, description: str = ""):
            def decorator(func):
                mock_mcp._prompts[name] = {"handler": func, "description": description}
                return func
            return decorator
        mock_mcp.prompt = capture_prompt
        AdminModule.construct(mcp=mock_mcp)
        return mock_mcp

    async def test_save_agent_to_tmpdir(self):
        mock_mcp = self._make_module()
        handler = mock_mcp._tools["vela_save"]["handler"]
        content = yaml.dump({"id": "test-save", "name": "Test Save Agent"})

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.mcp.modules.vela_module._TARGET_DIRS", {"agent": tmpdir, "workflow": tmpdir, "resource": tmpdir}):
                result = json.loads(await handler(type="agent", content=content))
                assert result["saved"] is True
                assert os.path.exists(os.path.join(tmpdir, "test-save.yaml"))

    async def test_save_workflow_auto_filename(self):
        mock_mcp = self._make_module()
        handler = mock_mcp._tools["vela_save"]["handler"]
        content = yaml.dump({
            "id": "test-wf",
            "name": "Test WF",
            "version": "2.0.0",
            "steps": [{"id": "s1", "type": "freeform", "prompt": "go"}],
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.mcp.modules.vela_module._TARGET_DIRS", {"agent": tmpdir, "workflow": tmpdir, "resource": tmpdir}):
                result = json.loads(await handler(type="workflow", content=content))
                assert result["saved"] is True
                assert os.path.exists(os.path.join(tmpdir, "test-wf@2.0.0.yaml"))

    async def test_save_creates_directory(self):
        mock_mcp = self._make_module()
        handler = mock_mcp._tools["vela_save"]["handler"]
        content = yaml.dump({"id": "test-mkdir", "name": "Test Mkdir"})

        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "subdir")
            with patch("src.mcp.modules.vela_module._TARGET_DIRS", {"agent": target, "workflow": target, "resource": target}):
                result = json.loads(await handler(type="agent", content=content))
                assert result["saved"] is True
                assert os.path.isdir(target)

    async def test_save_invalid_content_not_saved(self):
        mock_mcp = self._make_module()
        handler = mock_mcp._tools["vela_save"]["handler"]
        content = yaml.dump({"id": "bad"})  # missing name for agent

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.mcp.modules.vela_module._TARGET_DIRS", {"agent": tmpdir}):
                result = json.loads(await handler(type="agent", content=content))
                assert result.get("valid") is False
                assert not os.path.exists(os.path.join(tmpdir, "bad.yaml"))


class TestVelaStatus:
    """Tests for vela_status tool."""

    def _make_module(self):
        from src.mcp.modules.vela_module import AdminModule
        reset_singleton(AdminModule)
        mock_mcp = make_mock_mcp()
        mock_mcp._prompts = {}
        def capture_prompt(name: str, description: str = ""):
            def decorator(func):
                mock_mcp._prompts[name] = {"handler": func, "description": description}
                return func
            return decorator
        mock_mcp.prompt = capture_prompt
        AdminModule.construct(mcp=mock_mcp)
        return mock_mcp

    async def test_status_returns_counts(self):
        mock_mcp = self._make_module()
        handler = mock_mcp._tools["vela_status"]["handler"]

        # Mock DB access
        with patch("src.mcp.modules.vela_module.async_session_factory") as mock_sf:
            mock_session = AsyncMock()
            mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

            # Patch the _do_status method on the AdminModule instance
            from src.mcp.modules.vela_module import AdminModule
            with patch.object(AdminModule.instance(), '_do_status') as mock_status:
                mock_status.return_value = json.dumps({
                    "agents": 0, "workflows": 0, "resources": 0,
                    "active_runs": 0, "projects": 0, "memories": 0,
                })
                result = json.loads(await mock_status())
                assert "agents" in result
                assert "workflows" in result
                assert "resources" in result
                assert "active_runs" in result
                assert "projects" in result
                assert "memories" in result


class TestVelaPrompts:
    """Tests for vela and vela_help prompts."""

    def _make_module(self):
        from src.mcp.modules.vela_module import AdminModule
        reset_singleton(AdminModule)
        mock_mcp = make_mock_mcp()
        mock_mcp._prompts = {}
        def capture_prompt(name: str, description: str = ""):
            def decorator(func):
                mock_mcp._prompts[name] = {"handler": func, "description": description}
                return func
            return decorator
        mock_mcp.prompt = capture_prompt
        AdminModule.construct(mcp=mock_mcp)
        return mock_mcp

    def test_vela_prompt_registered(self):
        mock_mcp = self._make_module()
        assert "vela" in mock_mcp._prompts

    def test_vela_help_prompt_registered(self):
        mock_mcp = self._make_module()
        assert "vela_help" in mock_mcp._prompts

    async def test_vela_prompt_content(self):
        mock_mcp = self._make_module()
        handler = mock_mcp._prompts["vela"]["handler"]
        content = await handler()
        assert "Vela" in content
        assert "Workspace Navigator" in content
        assert "vela_advance_workflow" in content

    async def test_vela_help_content(self):
        mock_mcp = self._make_module()
        handler = mock_mcp._prompts["vela_help"]["handler"]
        content = await handler()
        assert "vela_validate" in content
        assert "vela_save" in content
        assert "vela_status" in content

    def test_three_tools_registered(self):
        mock_mcp = self._make_module()
        assert "vela_validate" in mock_mcp._tools
        assert "vela_save" in mock_mcp._tools
        assert "vela_status" in mock_mcp._tools
