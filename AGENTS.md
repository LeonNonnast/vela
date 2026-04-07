# AGENTS.md

## Project: Vela

**Stateful workflows for MCP servers. Open source. Self-hosted.**

Vela solves a fundamental problem: MCP servers have tools, but tools without process are just a bag of functions. Every MCP server that needs multi-step user guidance, state management, or structured interactions benefits from Vela.

**Two products, one repo:**

1. **vela-sdk** (`packages/vela-sdk/`) — Standalone workflow engine library. Any FastMCP server can add stateful workflows with 3 lines of code. Published as `vela-sdk` on PyPI.
2. **Vela Server** — Complete self-hosted MCP server with memory, workflows, resources, agents, and module hub. Uses vela-sdk internally.

### Who uses what

- **MCP developers** building their own servers → `pip install vela-sdk[fastmcp]`, define YAML workflows, ship
- **Developers/teams** who want a ready-made AI assistant layer → self-host Vela Server, connect via Claude Code/Cursor/etc.
- **Workflow authors** → use Vela's built-in workflow builder (AI-driven) to design processes, output YAML into projects or GitHub repos

### The developer loop

Vela is both the development tool and the runtime: connect Vela as MCP server → use its workflow builder to design your process → Vela outputs YAML → integrate vela-sdk in your MCP server → ship.

## Tech Stack

- Python 3.12+, FastMCP 3.x, FastAPI, SQLAlchemy (async), SQLite/MySQL, Pydantic v2
- Package manager: `uv` (workspace with `packages/vela-sdk`)
- Testing: `pytest` with `pytest-asyncio` (auto mode)
- SDK: `vela-sdk` — zero-dep core (pydantic, pyyaml, structlog), optional `[sqlalchemy]` and `[fastmcp]`

## Commands

```bash
# Vela Server
uv run pytest                                    # All tests
uv run pytest -x -v                              # Verbose, stop on first failure
uv run python -m src.mcp.server --stdio          # MCP Server (stdio for Claude Code)
uv run uvicorn src.mcp.server:app --port 8000    # MCP Server (HTTP)
uv run uvicorn src.api.app:app --port 8001       # API Server (dashboard + REST)
docker compose up                                # Both services

# vela-sdk
cd packages/vela-sdk && uv run pytest            # SDK tests (64)
cd packages/vela-sdk && uv run pytest -x -v      # SDK verbose
```

## Repository Structure

```
packages/
  vela-sdk/                    # Standalone workflow engine SDK (PyPI: vela-sdk)
    pyproject.toml             # pydantic, pyyaml, structlog + optional [sqlalchemy, fastmcp]
    src/vela_sdk/
      __init__.py              # Public API: VelaWorkflows, WorkflowEngine, schemas
      schemas/
        workflow.py            # WorkflowDefinition, StepDefinition, StepType, CaptureDefinition
        resource.py            # ResourceDefinition, ResourceReference
      engine/
        types.py               # WorkflowRunState (dataclass), AdvanceResult, WorkflowRunStatus
        workflow_engine.py     # Orchestrator: start/resume, advance, resolve_next
        dialog_handler.py      # Dialog phase management (advance_dialog, phases, prompts)
        prompt_builder.py      # Prompt assembly, template resolution
        lifecycle.py           # Auto-cancel rules (LifecycleChecker)
      loader/
        workflow_loader.py     # YAML loading with semver parsing
      storage/
        protocol.py            # WorkflowStore (typing.Protocol)
        memory.py              # InMemoryStore (for tests)
        sqlalchemy.py          # SQLAlchemyStore (standalone ORM, no FK deps)
      fastmcp/
        integration.py         # VelaWorkflows — thin orchestrator, tool registration
        elicitation.py         # CaptureDefinition → ctx.elicit() mapping
        auto_advance.py        # Auto-advance loop (elicit → advance → repeat)
        response_builder.py    # JSON response formatting
        session_elicitor.py    # User elicitation flows
    tests/                     # 64 SDK tests

src/
  shared/                      # Shared code (DB, services, config) for both services
    config/                    # App config (env vars, directories, ports)
    db/
      base.py                  # SQLAlchemy DeclarativeBase
      database.py              # Async engine + session factory
      models.py                # Project, Memory, WorkflowRun, ModuleSource
    repositories/              # Generic CRUD + domain queries (BaseSQLAlchemyRepository[T])
    schemas/                   # Pydantic models (workflow, agent, resource)
    services/
      project_service.py       # ProjectService — CRUD for projects, session management
      memory_service.py        # MemoryService — remember, recall, get, forget
      workflow_loader.py       # Workflow + agent YAML loader
      workflow_store_adapter.py  # VelaWorkflowStore: bridges WorkflowRepository → SDK protocol
      agent_loader.py          # Agent YAML loader
      github_api_service.py    # GitHub REST API client (httpx)
      resource_loader.py       # Resource YAML loader
      module_registry_service.py  # Module discovery & caching
      mcp_orchestrator.py      # MCP orchestration service

  api/                         # Vela API (FastAPI) — port 8001
    app.py                     # FastAPI app factory
    routes/                    # health, repos, pages
    static/                    # HTML, CSS, JS

  mcp/                         # Vela MCP (FastMCP 3.0) — port 8000
    server.py                  # FastMCP entry point (stdio + HTTP)
    module_registry.py         # Module registration (register_all_modules)
    modules/
      base.py                  # VelaModuleBase — shared singleton + construct/reset
      context_module.py        # vela_set/get/list_project (delegates to ProjectService)
      memory_module.py         # vela_remember/recall/get_memory/forget (delegates to MemoryService)
      workflow_module.py       # vela_advance/status/list_workflows (uses SDK engine)
      resource_module.py       # vela_list/get_resource
      agent_module.py          # vela_list_agents
      module_hub_module.py     # GitHub repo management (7 tools)
      vela_module.py           # AdminModule — vela_validate/save/status

tests/                         # Tests
Dockerfile.api / Dockerfile.mcp / docker-compose.yml
```

## Architecture

### Two Services, One Database

```
┌─────────────────────────────────────────────────────────┐
│              Shared Database (SQLite / MySQL)            │
└─────────────────────────────────────────────────────────┘
        ↑                                       ↑
  ┌───────────┐                          ┌───────────┐
  │ API :8001 │                          │ MCP :8000 │
  │ (FastAPI) │                          │ (FastMCP) │
  └───────────┘                          └───────────┘
       ↓                                      ↓
    Humans (Browser)                    AI Assistants (Claude, etc.)
```

No direct HTTP calls between services — DB-only communication. No authentication layer — both services are open.

### SDK Architecture

```
VelaWorkflows (thin orchestrator)
  ├── ResponseBuilder (JSON formatting)
  ├── SessionElicitor (elicitation flows)
  └── WorkflowEngine (orchestrator)
        ├── DialogHandler (dialog phases)
        ├── PromptBuilder (templates)
        ├── LifecycleChecker (auto-cancel)
        └── WorkflowStore (Protocol)
              └── InMemoryStore / SQLAlchemyStore
```

Vela Server uses the SDK via `VelaWorkflowStore` adapter, bridging `WorkflowRepository` (ORM) → `WorkflowStore` (protocol). The SDK engine works with `WorkflowRunState` dataclasses (dicts), not ORM objects (JSON strings).

### Service Layer + Dependency Injection

MCP modules are thin wrappers that delegate to service classes. Services encapsulate session management and business logic:

```
server.py → module_registry.py → Module.construct(mcp, service=...)
                                      │
                                  VelaModuleBase (singleton management)
                                      │
                                  ProjectService / MemoryService / etc.
                                      │
                                  Repository (ORM)
```

### Key Patterns

- **Module Base Class**: `VelaModuleBase` in `src/mcp/modules/base.py` — shared singleton via `construct()`/`reset()`, all 7 modules inherit from it
- **Module Registry**: `src/mcp/module_registry.py` — `register_all_modules(mcp, services)` wires modules to services
- **Dependency Injection**: Modules receive services via constructor, no direct `async_session_factory()` calls in modules
- **Service Layer**: `ProjectService`, `MemoryService` etc. encapsulate DB access and business logic
- **Protocol-based Storage**: SDK engine depends on `WorkflowStore` protocol
- **Adapter Pattern**: `VelaWorkflowStore` adapts ORM repo → SDK protocol
- **Direct Imports**: All imports go to `src.shared.*`, `src.mcp.*`, or `vela_sdk.*` (no shims/re-exports)
- **3-Provider Module Storage**: Modules can be stored on local filesystem (`provider="local"`), in database (`provider="db"`), or on GitHub (`provider="github"`). Module Hub tools accept a `source` parameter.
- **Unified Module Discovery**: All three content modules (`WorkflowModule`, `AgentModule`, `ResourceModule`) merge definitions from filesystem (bundled + user) and `ModuleRegistryService` (DB/local/GitHub modules). Priority: user filesystem > bundled > registry. Async methods (`_get_all_workflows()`, `_get_all_agents()`, `_get_all_resources()`) include DB sources; sync properties (`_workflows`, `_agents`, `_resources`) return filesystem only for backward compatibility.

## Workflow Engine (7 Step Types)

| Type | Description |
|------|-------------|
| `freeform` | Open-ended text input |
| `choice` | Select from options (with branching via `next`) |
| `confirm` | Yes/no confirmation |
| `execute` | Agent performs task, reports back |
| `dialog` | Multi-phase conversation (brainstorming, review, planning, requirements) |
| `workflow` | Delegate to sub-workflow |
| `mcp_call` | Server-side tool call |

Key features: template resolution (`{{params.X}}`, `{{state.X}}`), `depends_on` for least-context, `capture` with elicitation (`always`/`if_missing`/`never`), auto-advance loop, identity-based run resume.

## MCP Tools (23)

| Module | Tools |
|--------|-------|
| Context | `vela_set_project`, `vela_get_project`, `vela_list_projects` |
| Memory | `vela_remember`, `vela_recall`, `vela_get_memory`, `vela_forget` |
| Workflow | `vela_advance_workflow`, `vela_workflow_status`, `vela_list_workflows` |
| Resource | `vela_list_resources`, `vela_get_resource` |
| Agent | `vela_list_agents` |
| Module Hub | `vela_clone_repo`, `vela_sync_repo`, `vela_remove_repo`, `vela_list_repos`, `vela_create_module`, `vela_push_to_module`, `vela_delete_from_module` |
| Admin | `vela_validate`, `vela_save`, `vela_status` |

## API Endpoints (7)

| Path | Description |
|------|-------------|
| `/health`, `/health/live`, `/health/ready` | Health checks |
| `/api/repos`, `/api/repos/install`, `/api/repos/remove`, `/api/repos/sync` | Module repos |
| `/`, `/dashboard` | HTML pages |

## Config Variables

| Variable | Service | Description |
|----------|---------|-------------|
| `DATABASE_URL` | Both | Shared database (default: SQLite) |
| `GITHUB_TOKEN` | MCP | GitHub Personal Access Token — optional, only for GitHub module hub operations |
| `VELA_MODULES` | MCP | Module filter — glob patterns, comma-separated (e.g. `migration-*,team-a-*`). Empty = load all |
| `VELA_LOCAL_MODULES_DIR` | Both | Local module storage (default: ~/.vela/modules) |
| `API_BASE_URL` | API | API base URL (default: http://localhost:8001) |
| `APP_BASE_URL` | MCP | MCP base URL (default: http://localhost:8000) |

## User Directories

- `~/.vela/workflows/` — Custom workflow YAMLs
- `~/.vela/agents/` — Custom agent YAMLs
- `~/.vela/resources/` — Custom resource YAMLs
- `~/.vela/connectors.yaml` — External MCP server connections
- `~/.vela/modules/` — Local module storage (workflows, agents, resources per module)
