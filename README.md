# Vela

**Stateful workflows for MCP servers. Open source. Self-hosted.**

Every MCP server eventually needs user guidance — multi-step processes, state management, structured interactions. Today, most MCP projects fail at this. Tools exist, but there's no flow. Vela solves that.

**Two ways to use Vela:**

- **vela-sdk** — Add stateful workflows to *your* MCP server with 3 lines of code
- **Vela Server** — A complete self-hosted MCP server with memory, workflows, resources, and a module hub

## The Problem

MCP servers have tools. But tools without process are just a bag of functions. The AI has to guess what comes next, state gets lost between sessions, and multi-step tasks fall apart.

**Example:** A cooking assistant MCP server has `search_recipe`, `get_ingredients`, `set_timer`, `next_step`. Without guidance, the AI calls them in random order. With Vela, it becomes a workflow: pick recipe → check ingredients → step-by-step cooking → timers per step. Pausable, resumable, stateful.

This applies everywhere — navigation, document search, CI/CD pipelines, onboarding flows, data migrations. Any process with more than one step benefits.

## vela-sdk — Workflows for Your MCP Server

```bash
pip install vela-sdk[fastmcp]
```

```python
from fastmcp import FastMCP
from vela_sdk import VelaWorkflows

mcp = FastMCP("cooking-assistant")
workflows = VelaWorkflows(mcp, workflows_dir="./workflows/")
```

Define your process as YAML:

```yaml
id: cook-recipe
name: Cook a Recipe
steps:
  - id: choose
    type: choice
    prompt: "What do you want to cook?"
    options:
      - key: pasta
        label: Pasta Carbonara
      - key: curry
        label: Thai Green Curry
  - id: ingredients
    type: confirm
    prompt: "Check these ingredients: {{state.recipe_ingredients}}"
  - id: cooking
    type: execute
    prompt: "Follow the recipe step by step."
    capture:
      - key: result
        elicit: never
```

That's it. Your MCP server now has a guided, stateful cooking process. The SDK registers the tools, manages state, handles branching, and supports pause/resume across sessions.

See [packages/vela-sdk/](packages/vela-sdk/) for the full SDK documentation.

## Vela Server — The Complete Package

For developers who want a ready-made AI assistant layer with memory, workflows, and resources:

```bash
git clone https://github.com/LeonNonnast/vela.git
cd vela && uv sync
uv run python -m src.mcp.server --stdio  # Works immediately, no config needed
```

No authentication required -- Vela starts immediately and you can begin building workflows right away.

Add to Claude Code MCP config:

```json
{
  "mcpServers": {
    "vela": {
      "command": "uv",
      "args": ["run", "python", "-m", "src.mcp.server", "--stdio"],
      "cwd": "/path/to/vela"
    }
  }
}
```

See [.env.example](.env.example) for all configuration options.

### What You Get (23 MCP Tools)

**Memory** — AI agents forget everything between sessions. Vela remembers.
- `vela_remember` / `vela_recall` / `vela_get_memory` / `vela_forget`
- Two-stage pattern: compact index first, full content on demand

**Workflows** — Define multi-step processes in YAML. Vela guides the AI automatically.
- `vela_advance_workflow` / `vela_workflow_status` / `vela_list_workflows`
- 7 step types: freeform, choice, confirm, execute, dialog, workflow (sub-workflows), mcp_call
- Dialog steps with built-in phases (brainstorming, review, planning, requirements)
- Auto-advance through non-interactive steps, elicitation for structured input

**Context** — Projects carry tech stack, conventions, and state.
- `vela_set_project` / `vela_get_project` / `vela_list_projects`

**Resources** — Reference material (schemas, examples, conventions) inline or on-demand.
- `vela_list_resources` / `vela_get_resource`

**Agents** — Personas defined in YAML, loaded as MCP prompts.
- `vela_list_agents`

**Module Hub** — Share workflows, agents, and resources across 3 storage backends.
- `vela_clone_repo` / `vela_sync_repo` / `vela_remove_repo` / `vela_list_repos`
- `vela_create_module` / `vela_push_to_module` / `vela_delete_from_module`
- **Local filesystem** (default) -- modules stored in `~/.vela/modules/`
- **Database** -- modules stored as DB entries
- **GitHub** -- connect GitHub repos
- Use the `source` parameter on module hub tools to select the storage backend

**Admin** — Validate, save, and inspect.
- `vela_validate` / `vela_save` / `vela_status`

### Build Workflows with Vela

Vela includes a workflow-builder workflow — use AI to design your processes:

1. Connect Vela as MCP server in your IDE
2. Use the workflow builder to design your process interactively
3. Vela generates the YAML and saves it to your project or a GitHub repo
4. Add `VelaWorkflows(mcp, workflows_dir="./workflows/")` to your MCP server
5. Ship it

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Shared Database (SQLite / MySQL)            │
│      Project, Memory, WorkflowRun, ModuleRegistry       │
└─────────────────────────────────────────────────────────┘
        ↑                                       ↑
  ┌───────────┐                          ┌───────────┐
  │ API :8001 │                          │ MCP :8000 │
  │ (FastAPI) │                          │ (FastMCP) │
  ├───────────┤                          ├───────────┤
  │ Dashboard │                          │ 23 Tools  │
  │ REST API  │                          │ Prompts   │
  └───────────┘                          │ Resources │
       ↓                                 └───────────┘
    Humans                                    ↓
  (Browser)                            AI Assistants
                                      (Claude, etc.)

  ┌───────────────────────────────────────────────────┐
  │                   vela-sdk (PyPI)                  │
  │  WorkflowEngine · DialogHandler · PromptBuilder   │
  │  VelaWorkflows · ResponseBuilder · SessionElicitor│
  │  Add workflows to any FastMCP server              │
  └───────────────────────────────────────────────────┘
```

**Vela Server** runs as two services with a shared database. The MCP server (port 8000) serves AI agents. The API server (port 8001) serves the web dashboard. No direct calls between them.

**vela-sdk** is the workflow engine extracted as a standalone package. Vela Server uses it internally. You can use it independently in your own MCP servers.

## Configuration

| Variable | Service | Description |
|----------|---------|-------------|
| `DATABASE_URL` | Both | Database connection (default: SQLite) |
| `GITHUB_CLIENT_ID` | Both | GitHub API client ID (for module hub) |
| `GITHUB_CLIENT_SECRET` | Both | GitHub API client secret (for module hub) |
| `VELA_LOCAL_MODULES_DIR` | Both | Local module storage (default: `~/.vela/modules`) |
| `API_BASE_URL` | API | API base URL (default: `http://localhost:8001`) |
| `APP_BASE_URL` | MCP | MCP base URL (default: `http://localhost:8000`) |

## Development

```bash
uv run pytest                             # All Vela tests
uv run pytest -x -v                       # Verbose, stop on first failure
cd packages/vela-sdk && uv run pytest     # SDK tests (64)
```

## Docker

```bash
docker compose up
```

Starts MCP server (port 8000) and API server (port 8001).

## Contributing

Contributions welcome! See [BRANDING.md](BRANDING.md) for naming and attribution guidelines.

## License

[MIT](LICENSE)
