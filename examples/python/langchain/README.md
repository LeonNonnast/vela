# Vela + LangChain Example

This example shows how to add Vela workflow tools to a LangChain ReAct agent.
The `VelaToolkit` loads YAML workflow definitions and exposes them as standard LangChain tools
that any agent can call to start, advance, and manage stateful workflows.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- `ANTHROPIC_API_KEY` environment variable

## Quick Start

```bash
export ANTHROPIC_API_KEY=your-key-here
uv sync
uv run python agent.py
```

## What to Try

Once the agent is running, try:

> "Start the project-setup workflow"

The agent will use the Vela tools to walk through the workflow steps: picking a project type, describing the project, and confirming the setup.
