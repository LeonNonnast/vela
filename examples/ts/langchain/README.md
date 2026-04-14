# Vela + LangChain (TypeScript)

Minimal example: use Vela workflows as LangChain tools inside a ReAct agent powered by Claude.

## Prerequisites

- Node.js 18+
- npm
- `ANTHROPIC_API_KEY` environment variable

## Quick Start

```bash
export ANTHROPIC_API_KEY=sk-ant-...
npm install
npm start
```

This starts an interactive CLI agent. The agent has access to Vela workflow tools and can guide you through the `project-setup` workflow conversationally.

## What to try

1. Type: "Start the project setup workflow for owner Alice"
2. The agent will call `workflow_advance` and walk you through each step.
3. Answer the prompts to choose a project type, describe your project, and confirm setup.
4. Type "exit" to quit.
