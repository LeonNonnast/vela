# Vela SDK Examples

Each example is a self-contained project demonstrating how to integrate `vela-sdk` with different frameworks.

## Python

| Example | Framework | Description |
|---------|-----------|-------------|
| [mcp-fastmcp](python/mcp-fastmcp/) | FastMCP | Minimal MCP server with workflows |
| [langchain](python/langchain/) | LangChain | ReAct agent with workflow tools |

## TypeScript

| Example | Framework | Description |
|---------|-----------|-------------|
| [mcp-fastmcp](ts/mcp-fastmcp/) | FastMCP | MCP server with FastMcpAdapter |
| [mcp-sdk](ts/mcp-sdk/) | @modelcontextprotocol/sdk | MCP server with official SDK |
| [langchain](ts/langchain/) | LangChain.js | ReAct agent with workflow tools |

## Shared Workflow

All examples use the same `project-setup` workflow — a 3-step guided setup (choose type, describe project, confirm). See any example's `workflows/project-setup.yaml`.
