# Vela

**Stateful workflows for MCP servers. Open source.**

Every MCP server eventually needs user guidance — multi-step processes, state management, structured interactions. Tools exist, but there's no flow. Vela solves that.

## The Problem

MCP servers have tools. But tools without process are just a bag of functions. The AI has to guess what comes next, state gets lost between sessions, and multi-step tasks fall apart.

**Example:** A cooking assistant MCP server has `search_recipe`, `get_ingredients`, `set_timer`, `next_step`. Without guidance, the AI calls them in random order. With Vela, it becomes a workflow: pick recipe → check ingredients → step-by-step cooking → timers per step. Pausable, resumable, stateful.

## Python

```bash
pip install vela-sdk[fastmcp]
```

```python
from fastmcp import FastMCP
from vela_sdk import VelaWorkflows

mcp = FastMCP("cooking-assistant")
workflows = VelaWorkflows(mcp, workflows_dir="./workflows/")
```

That's it. Your MCP server now has guided, stateful processes. The SDK registers the tools, manages state, handles branching, and supports pause/resume across sessions.

See [packages/vela-sdk/](packages/vela-sdk/) for the full SDK documentation.

## TypeScript

```bash
npm install vela-sdk
```

```typescript
import { FastMCP } from "fastmcp";
import { VelaWorkflows } from "vela-sdk";
import { FastMcpAdapter } from "vela-sdk/adapters/fastmcp";

const server = new FastMCP({ name: "my-server", version: "1.0.0" });
const vela = new VelaWorkflows({
  server: new FastMcpAdapter(server),
  workflows: [myWorkflowYaml],
});
```

Also supports `@modelcontextprotocol/sdk` and LangChain adapters.

See [packages/vela-sdk-ts/](packages/vela-sdk-ts/) for the full TypeScript SDK documentation.

## Define Your Process as YAML

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

7 step types: `freeform`, `choice`, `confirm`, `execute`, `dialog`, `workflow` (sub-workflows), `mcp_call`. Template resolution, branching, auto-advance, identity-based resume, and structured input collection via elicitation.

## Examples

| Example | Framework | Language |
|---------|-----------|----------|
| [mcp-fastmcp](examples/python/mcp-fastmcp/) | FastMCP | Python |
| [langchain](examples/python/langchain/) | LangChain | Python |
| [mcp-fastmcp](examples/ts/mcp-fastmcp/) | FastMCP | TypeScript |
| [mcp-sdk](examples/ts/mcp-sdk/) | @modelcontextprotocol/sdk | TypeScript |
| [langchain](examples/ts/langchain/) | LangChain | TypeScript |

## Architecture

```
VelaWorkflows (integration layer)
       │
  WorkflowEngine (state machine)
       │
  WorkflowStore (Protocol)
       │
  InMemoryStore / SQLAlchemyStore / LocalStorageStore
```

Both SDKs share the same architecture: a pluggable state machine with protocol-based storage and framework adapters.

## Project Structure

```
packages/
  vela-sdk/              # Python SDK (PyPI: vela-sdk)
  vela-sdk-ts/           # TypeScript SDK (npm: vela-sdk)
examples/
  python/                # Python examples (FastMCP, LangChain)
  ts/                    # TypeScript examples (FastMCP, MCP SDK, LangChain)
modules/
  vela/                  # Bundled workflows, agents, and resources (YAML)
schemas/                 # JSON Schema definitions for workflows, agents, resources
```

## Development

```bash
cd packages/vela-sdk && uv run pytest          # Python SDK tests
cd packages/vela-sdk-ts && npm test            # TypeScript SDK tests
cd packages/vela-sdk-ts && npm run build       # TypeScript SDK build
```

## License

[MIT](LICENSE)
