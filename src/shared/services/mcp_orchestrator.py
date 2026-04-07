"""MCP Orchestrator — manages connections to external MCP servers.

Provides server-side tool calling capability for:
- fetch: Pre-step data retrieval
- mcp_call: Direct tool invocation step type
- Tool namespace exposure per step
"""

import os
from typing import Any, Optional

import structlog

from src.shared.config.connectors import ConnectorConfig, load_connectors

logger = structlog.get_logger()


class MCPOrchestrator:
    """Orchestrates connections to external MCP servers."""

    def __init__(self, connectors: Optional[dict[str, ConnectorConfig]] = None):
        self._connectors = connectors or {}

    @classmethod
    def from_config(cls, config_path: Optional[str] = None) -> "MCPOrchestrator":
        """Create orchestrator from config file."""
        connectors = load_connectors(config_path)
        return cls(connectors=connectors)

    @property
    def connectors(self) -> dict[str, ConnectorConfig]:
        return self._connectors

    def get_connector(self, connector_id: str) -> Optional[ConnectorConfig]:
        """Get connector configuration by ID."""
        return self._connectors.get(connector_id)

    def list_connectors(self) -> list[dict[str, str]]:
        """List available connectors."""
        return [
            {"id": c.id, "name": c.name, "transport": c.transport}
            for c in self._connectors.values()
        ]

    async def call_tool(
        self,
        connector_id: str,
        tool_name: str,
        params: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Call a tool on an external MCP server.

        Creates a temporary client connection, calls the tool, and returns the result.
        """
        connector = self.get_connector(connector_id)
        if not connector:
            raise ValueError(f"Connector not found: {connector_id}")

        command = self._build_command(connector)
        if not command:
            raise ValueError(f"Cannot build command for connector: {connector_id}")

        try:
            from fastmcp import Client

            # Set environment for the subprocess
            env = {**os.environ, **connector.env}

            async with Client(command, env=env) as client:
                result = await client.call_tool(tool_name, params or {})
                return self._extract_result(result)
        except Exception as e:
            logger.error(
                "orchestrator.call_tool_error",
                connector=connector_id,
                tool=tool_name,
                error=str(e),
            )
            raise

    async def list_tools(self, connector_id: str) -> list[dict[str, Any]]:
        """List available tools on an external MCP server."""
        connector = self.get_connector(connector_id)
        if not connector:
            raise ValueError(f"Connector not found: {connector_id}")

        command = self._build_command(connector)
        if not command:
            raise ValueError(f"Cannot build command for connector: {connector_id}")

        try:
            from fastmcp import Client

            env = {**os.environ, **connector.env}

            async with Client(command, env=env) as client:
                tools = await client.list_tools()
                return [
                    {"name": t.name, "description": t.description or ""}
                    for t in tools
                ]
        except Exception as e:
            logger.error(
                "orchestrator.list_tools_error",
                connector=connector_id,
                error=str(e),
            )
            raise

    async def execute_fetch(
        self,
        fetch_source: str,
        fetch_action: str,
        fetch_params: dict[str, Any],
    ) -> Any:
        """Execute a fetch definition — call a tool on a mounted server.

        Maps to: fetch.source -> connector_id, fetch.action -> tool_name
        """
        return await self.call_tool(fetch_source, fetch_action, fetch_params)

    def _build_command(self, connector: ConnectorConfig) -> Optional[str]:
        """Build the command string for a stdio connector."""
        if connector.transport == "stdio" and connector.command:
            parts = [connector.command] + connector.args
            return " ".join(parts)
        if connector.transport == "http" and connector.url:
            return connector.url
        return None

    @staticmethod
    def _extract_result(result: Any) -> Any:
        """Extract text content from a tool call result."""
        if isinstance(result, str):
            return result
        if isinstance(result, list) and len(result) > 0:
            first = result[0]
            if hasattr(first, "text"):
                return first.text
            return str(first)
        if hasattr(result, "content"):
            content = result.content
            if isinstance(content, list) and len(content) > 0:
                return content[0].text if hasattr(content[0], "text") else str(content[0])
            return str(content)
        return str(result)
