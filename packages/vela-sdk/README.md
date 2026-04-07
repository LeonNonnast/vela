# vela-sdk

**Stateful workflows for MCP servers.** Add guided, multi-step processes to any FastMCP server — with 3 lines of code.

## The Problem

MCP servers have tools. But tools without process are just a bag of functions. The AI has to guess what comes next, state gets lost between sessions, and multi-step tasks fall apart.

**Every MCP server that does more than simple lookups eventually needs user guidance.** A cooking assistant needs a recipe flow. A navigation server needs a route-planning process. A CI/CD server needs a deployment pipeline. Today, every MCP developer builds this from scratch — or doesn't build it at all.

## The Solution

```bash
pip install vela-sdk[fastmcp]
```

```python
from fastmcp import FastMCP
from vela_sdk import VelaWorkflows

mcp = FastMCP("my-server")
workflows = VelaWorkflows(mcp, workflows_dir="./workflows/")
```

This registers 3 MCP tools and a prompt per workflow:

| Tool | Description |
|------|-------------|
| `workflow_advance` | Start, resume, or advance a workflow run |
| `workflow_status` | Get run status by ID |
| `workflow_list` | List definitions and active runs |

Your MCP server now has guided, stateful processes. Pausable, resumable, with branching and structured input collection.

## Define Your Process as YAML

```yaml
id: onboarding
name: User Onboarding
version: 1.0.0
params:
  - name: username
    required: true
    identity: true
steps:
  - id: welcome
    type: freeform
    prompt: "Welcome {{params.username}}! Tell me about your project."
    capture:
      - key: project_description
        elicit: never
  - id: confirm
    type: confirm
    prompt: "Got it: {{state.project_description}}. Ready to proceed?"
```

### Step Types

| Type | Description |
|------|-------------|
| `freeform` | Open-ended text input |
| `choice` | Select from defined options (with branching) |
| `confirm` | Yes/no confirmation |
| `execute` | Agent performs a task, then reports back |
| `dialog` | Multi-phase interactive conversation (brainstorming, review, etc.) |
| `workflow` | Delegate to a sub-workflow |
| `mcp_call` | Call an external MCP tool |

### Key Features

- **State management** — Workflow runs persist across sessions. Resume where you left off.
- **Identity-based resume** — Same params = same run. No duplicate processes.
- **Template resolution** — `{{params.X}}`, `{{state.X}}`, `{{steps.step_id.key}}`
- **Least-context principle** — `depends_on` declares what each step needs. No context overload.
- **Captures & elicitation** — Collect structured data via `ctx.elicit()` or agent output.
- **Auto-advance** — Engine automatically progresses through non-interactive steps.
- **Branching** — Choice options can route to different steps.
- **Sub-workflows** — Compose complex processes from reusable parts.
- **Dialog phases** — Built-in modes for brainstorming, review, planning, requirements.

## Architecture

```
VelaWorkflows (FastMCP integration)
       │
  WorkflowEngine (state machine)
       │
  WorkflowStore (Protocol)
       │
  InMemoryStore / SQLAlchemyStore
```

| Component | Description |
|-----------|-------------|
| `VelaWorkflows` | Main entry point. Registers MCP tools + prompts. |
| `WorkflowEngine` | State machine. Step advancement, branching, templates, dialog phases. |
| `WorkflowStore` | Protocol — swap storage without changing engine code. |
| `InMemoryStore` | For testing and prototyping. No dependencies. |
| `SQLAlchemyStore` | Production store. Auto-creates tables. |

### Custom Storage

Implement the `WorkflowStore` protocol for any backend:

```python
class WorkflowStore(Protocol):
    async def create_run(...) -> WorkflowRunState: ...
    async def update_step(...) -> WorkflowRunState: ...
    async def get_by_id(...) -> Optional[WorkflowRunState]: ...
    async def find_by_identity(...) -> Optional[WorkflowRunState]: ...
    async def list_active(...) -> list[WorkflowRunState]: ...
    async def commit(self) -> None: ...
```

## Configuration

```python
VelaWorkflows(
    mcp,                                    # FastMCP server instance
    store=InMemoryStore(),                  # Storage backend (default: InMemoryStore)
    workflows_dir="./workflows/",           # YAML directory (or list of dirs)
    resource_resolver=my_resolver,          # Optional: resolve resource references
    tool_prefix="workflow",                 # Tool name prefix (default: "workflow")
    auto_advance=True,                      # Auto-advance non-interactive steps
    register_prompts=True,                  # Register MCP prompts per workflow
)
```

## Optional Dependencies

```bash
pip install vela-sdk                # Core only (schemas, engine, InMemoryStore)
pip install vela-sdk[sqlalchemy]    # + SQLAlchemyStore
pip install vela-sdk[fastmcp]       # + VelaWorkflows FastMCP integration
pip install vela-sdk[all]           # Everything
```

## Building Workflows with Vela

The [Vela Server](https://github.com/LeonNonnast/vela) includes an AI-driven workflow builder. Connect it as an MCP server, describe your process, and it generates the YAML — directly into your project directory. Then integrate with vela-sdk and ship.

## Development

```bash
cd packages/vela-sdk
uv sync
uv run pytest -v        # 64 tests
```

## License

[MIT](../../LICENSE)
