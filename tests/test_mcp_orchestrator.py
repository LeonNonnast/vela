"""MCP Orchestrator Tests — config loading, command building, tool calling."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from src.shared.config.connectors import ConnectorConfig, load_connectors
from src.shared.services.mcp_orchestrator import MCPOrchestrator


class TestConnectorConfig:
    def test_load_connectors_from_yaml(self, tmp_path):
        config = {
            "connectors": [
                {
                    "id": "test-server",
                    "name": "Test MCP Server",
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "@test/server"],
                },
            ]
        }
        filepath = tmp_path / "connectors.yaml"
        filepath.write_text(yaml.dump(config))

        result = load_connectors(str(filepath))
        assert len(result) == 1
        assert "test-server" in result
        assert result["test-server"].name == "Test MCP Server"
        assert result["test-server"].command == "npx"

    def test_load_connectors_with_env_vars(self, tmp_path):
        config = {
            "connectors": [
                {
                    "id": "github",
                    "name": "GitHub",
                    "command": "npx",
                    "args": ["-y", "@mcp/github"],
                    "env": {"GITHUB_TOKEN": "${TEST_TOKEN}"},
                },
            ]
        }
        filepath = tmp_path / "connectors.yaml"
        filepath.write_text(yaml.dump(config))

        with patch.dict(os.environ, {"TEST_TOKEN": "my-secret-token"}):
            result = load_connectors(str(filepath))
            assert result["github"].env["GITHUB_TOKEN"] == "my-secret-token"

    def test_load_connectors_file_not_found(self):
        result = load_connectors("/nonexistent/path.yaml")
        assert result == {}

    def test_load_connectors_empty_file(self, tmp_path):
        filepath = tmp_path / "connectors.yaml"
        filepath.write_text("")
        result = load_connectors(str(filepath))
        assert result == {}

    def test_load_connectors_no_connectors_key(self, tmp_path):
        filepath = tmp_path / "connectors.yaml"
        filepath.write_text(yaml.dump({"other": "stuff"}))
        result = load_connectors(str(filepath))
        assert result == {}


class TestMCPOrchestrator:
    def test_from_config_no_file(self):
        orch = MCPOrchestrator.from_config("/nonexistent/path.yaml")
        assert orch.connectors == {}

    def test_list_connectors(self):
        connectors = {
            "github": ConnectorConfig(id="github", name="GitHub", command="npx", args=["-y", "@mcp/github"]),
            "fs": ConnectorConfig(id="fs", name="Filesystem", command="npx", args=["-y", "@mcp/fs"]),
        }
        orch = MCPOrchestrator(connectors=connectors)
        result = orch.list_connectors()
        assert len(result) == 2
        ids = {c["id"] for c in result}
        assert ids == {"github", "fs"}

    def test_get_connector(self):
        connectors = {
            "github": ConnectorConfig(id="github", name="GitHub", command="npx"),
        }
        orch = MCPOrchestrator(connectors=connectors)
        assert orch.get_connector("github") is not None
        assert orch.get_connector("nonexistent") is None

    def test_build_command_stdio(self):
        connector = ConnectorConfig(
            id="test", name="Test", transport="stdio",
            command="npx", args=["-y", "@test/server"],
        )
        orch = MCPOrchestrator()
        cmd = orch._build_command(connector)
        assert cmd == "npx -y @test/server"

    def test_build_command_http(self):
        connector = ConnectorConfig(
            id="test", name="Test", transport="http",
            url="http://localhost:3000/mcp",
        )
        orch = MCPOrchestrator()
        cmd = orch._build_command(connector)
        assert cmd == "http://localhost:3000/mcp"

    def test_build_command_no_command(self):
        connector = ConnectorConfig(id="test", name="Test", transport="stdio")
        orch = MCPOrchestrator()
        cmd = orch._build_command(connector)
        assert cmd is None

    @pytest.mark.asyncio
    async def test_call_tool_connector_not_found(self):
        orch = MCPOrchestrator()
        with pytest.raises(ValueError, match="Connector not found"):
            await orch.call_tool("nonexistent", "some_tool")

    @pytest.mark.asyncio
    async def test_execute_fetch(self):
        """execute_fetch delegates to call_tool."""
        orch = MCPOrchestrator(connectors={
            "devops": ConnectorConfig(id="devops", name="DevOps", command="npx", args=["server"]),
        })

        with patch.object(orch, "call_tool", new_callable=AsyncMock, return_value="fetch-result") as mock_call:
            result = await orch.execute_fetch("devops", "get_status", {"env": "prod"})
            assert result == "fetch-result"
            mock_call.assert_awaited_once_with("devops", "get_status", {"env": "prod"})

    def test_extract_result_string(self):
        assert MCPOrchestrator._extract_result("hello") == "hello"

    def test_extract_result_list(self):
        mock_content = MagicMock()
        mock_content.text = "from list"
        assert MCPOrchestrator._extract_result([mock_content]) == "from list"
