# Vela + @modelcontextprotocol/sdk (TypeScript)

Minimal example: add stateful workflows to an MCP server built with the [official MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk) using the Vela SDK.

## Prerequisites

- Node.js 18+
- npm

## Quick Start

```bash
npm install
npm start
```

The server starts on **stdio** and exposes three workflow tools (`workflow_advance`, `workflow_status`, `workflow_list`) plus an MCP prompt for the `project-setup` workflow. This adapter also supports MCP elicitation for interactive parameter collection.

## MCP Config for Claude Code

Add to your Claude Code MCP config (`~/.claude/mcp.json`):

```json
{
  "mcpServers": {
    "project-assistant": {
      "command": "npx",
      "args": ["tsx", "server.ts"],
      "cwd": "/path/to/this/directory"
    }
  }
}
```

## What to try

1. Use the `workflow_project-setup` prompt to start the guided project setup.
2. Or call `workflow_advance` with `{"workflow_id": "project-setup", "params": "{\"owner\": \"Alice\"}"}` to start directly.
3. Follow the `next_action` instructions in each response to advance through the workflow steps.
