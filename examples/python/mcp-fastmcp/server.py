"""Minimal MCP server with Vela workflow support."""

from fastmcp import FastMCP
from vela_sdk import VelaWorkflows

mcp = FastMCP("project-assistant")

# One line to add stateful workflows — reads YAML from ./workflows/
workflows = VelaWorkflows(mcp, workflows_dir="./workflows/")

if __name__ == "__main__":
    mcp.run(transport="stdio")
