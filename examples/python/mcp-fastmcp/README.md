# Vela + FastMCP Example

Three lines of code turn a standard FastMCP server into a workflow-powered assistant.
Vela reads YAML workflow definitions and registers MCP tools and prompts automatically.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## Quick Start

```bash
uv sync
uv run python server.py
```

## MCP Configuration

Add this to your Claude Code MCP config (`.mcp.json` or Claude Desktop settings):

```json
{
  "mcpServers": {
    "project-assistant": {
      "command": "uv",
      "args": ["run", "python", "server.py"],
      "cwd": "/path/to/examples/python/mcp-fastmcp"
    }
  }
}
```

## What to Try

Once the server is connected, ask your assistant:

> "Start the project-setup workflow"

The assistant will walk you through picking a project type, describing the project, and confirming the setup — all driven by the YAML definition in `workflows/project-setup.yaml`.
