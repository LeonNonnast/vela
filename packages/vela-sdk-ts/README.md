# vela-sdk

TypeScript Workflow Engine for MCP Servers.

Add structured, multi-step workflows to any MCP server. Define workflows in YAML, vela-sdk registers the tools and prompts, drives the state machine, and handles elicitation dialogs automatically.

## Quick Start

```typescript
import { FastMCP } from "fastmcp";
import { VelaWorkflows } from "vela-sdk";
import { FastMcpAdapter } from "vela-sdk/adapters/fastmcp";

const server = new FastMCP({ name: "my-server", version: "1.0.0" });

const workflows = new VelaWorkflows({
  server: new FastMcpAdapter(server),
  workflows: [myWorkflowYaml],   // YAML strings
  agents: [myAgentYaml],         // optional
});

server.start({ transportType: "stdio" });
```

The constructor parses the YAML, registers MCP tools (`workflow_advance`, `workflow_status`, `workflow_list`) and prompts, and is ready to serve.

## Features

- **YAML-defined workflows** with typed steps: `execute`, `input`, `choice`, `confirm`, `dialog`, `workflow` (sub-workflows)
- **Automatic state machine** -- advance, branch, loop, sub-workflow delegation, and completion
- **MCP elicitation** -- collects required captures via native MCP elicitation dialogs (no manual prompting)
- **Auto-advance loop** -- agent-driven steps execute without user intervention
- **Agent personas** -- YAML-defined agents with persona, greeting, and workflow lists
- **Sub-workflows** with automatic parameter mapping and parent resume
- **Pluggable storage** -- in-memory (default), localStorage/KV, or bring your own `WorkflowStore`
- **Pluggable engine** -- swap the `IWorkflowEngine` for custom state machine logic
- **Extension protocols** -- `WorkflowResolver`, `SessionProvider`, `ParamFilter`, `ProjectResolver`
- **Locale support** -- English and German built-in, extensible via the `Locale` interface
- **Dual adapter system** -- `fastmcp` and `@modelcontextprotocol/sdk` supported out of the box
- **Dual module format** -- ESM and CommonJS builds via tsup

## Installation

```bash
npm install vela-sdk
```

Plus one MCP framework (peer dependency, both optional):

```bash
# Option A: FastMCP
npm install fastmcp

# Option B: Official MCP SDK
npm install @modelcontextprotocol/sdk
```

## Usage

### Workflow YAML Format

```yaml
id: onboarding
version: "1"
name: Employee Onboarding
description: Onboard a new team member
params:
  - name: employee_name
    type: string
    required: true
    identity: true
    label: Employee Name
steps:
  - id: collect_info
    type: input
    name: Collect Information
    prompt: "Please provide the department and start date."
    capture:
      - key: department
        source: elicit
        label: Department
        required: true
      - key: start_date
        source: elicit
        label: Start Date
        required: true
  - id: setup_accounts
    type: execute
    name: Set Up Accounts
    prompt: "Create accounts for {{employee_name}} in {{department}}."
  - id: confirm_complete
    type: confirm
    name: Confirm Completion
    prompt: "All accounts created for {{employee_name}}. Confirm onboarding is complete."
```

Template variables use `{{param_name}}` syntax and resolve from workflow params and captured state data.

### Agent Personas

```yaml
id: hr-assistant
name: HR Assistant
persona: You are a helpful HR assistant that guides managers through employee workflows.
greeting: Hello! I can help you with onboarding, offboarding, and other HR workflows.
workflows:
  - onboarding
  - offboarding
```

Pass agent YAML strings via the `agents` option. They register as MCP prompts (`agent_<id>`).

### Custom Storage

The default `InMemoryStore` loses state on restart. For persistence, use `LocalStorageStore` with any `KVStorage` backend:

```typescript
import { VelaWorkflows, LocalStorageStore } from "vela-sdk";

// KVStorage interface: getItem, setItem, removeItem (sync or async)
const store = new LocalStorageStore(localStorage);
// or: new LocalStorageStore(myRedisAdapter, "myapp:")

const workflows = new VelaWorkflows({
  server: adapter,
  store,
  workflows: [yaml],
});
```

Implement the full `WorkflowStore` interface for custom backends (databases, APIs):

```typescript
interface WorkflowStore {
  findByIdentity(workflowId: string, identityParams: Record<string, string>): Promise<WorkflowRunState | null>;
  createRun(options: CreateRunOptions): Promise<WorkflowRunState>;
  updateStep(runId: string, stepId: string | null, options?: UpdateStepOptions): Promise<WorkflowRunState>;
  getById(runId: string): Promise<WorkflowRunState | null>;
  listActive(options?: ListActiveOptions): Promise<WorkflowRunState[]>;
  commit(): Promise<void>;
}
```

### Custom Engine

Replace the default state machine with a custom `IWorkflowEngine`:

```typescript
import { VelaWorkflows, type IWorkflowEngine } from "vela-sdk";

class MyEngine implements IWorkflowEngine {
  // Implement: startOrResume, advance, assemblePrompt, getStep,
  //            checkLifecycle, validateDependsOn, handleOnError
}

const workflows = new VelaWorkflows({
  server: adapter,
  engine: new MyEngine(),
  workflows: [yaml],
});
```

### Locale

```typescript
import { VelaWorkflows, getLocale } from "vela-sdk";

// Built-in: "en" (default), "de"
const workflows = new VelaWorkflows({
  server: adapter,
  locale: getLocale("de"),
  workflows: [yaml],
});
```

Provide a custom `Locale` object to translate all user-facing strings.

### Tool Name Customization

```typescript
const workflows = new VelaWorkflows({
  server: adapter,
  toolPrefix: "wf",                         // default: "workflow"
  toolNameFormat: { advance: "do_step" },    // override individual names
  workflows: [yaml],
});
// Registers: do_step, wf_status, wf_list
```

### Extension Protocols

Plug in custom logic for advanced scenarios:

```typescript
import type {
  WorkflowResolver,
  SessionProvider,
  ParamFilter,
  ProjectResolver,
} from "vela-sdk";

const workflows = new VelaWorkflows({
  server: adapter,
  workflows: [yaml],

  // Load workflows from a database or API instead of in-memory
  workflowResolver: myDbResolver,

  // Provide per-request WorkflowStore instances (e.g. DB transactions)
  sessionProvider: mySessionProvider,

  // Control which missing params trigger elicitation
  paramFilter: myParamFilter,

  // Resolve project slugs to IDs
  projectResolver: myProjectResolver,
});
```

## Adapters

### FastMCP

```typescript
import { FastMCP } from "fastmcp";
import { FastMcpAdapter } from "vela-sdk/adapters/fastmcp";

const server = new FastMCP({ name: "my-server", version: "1.0.0" });
const adapter = new FastMcpAdapter(server);

const workflows = new VelaWorkflows({
  server: adapter,
  workflows: [yaml],
});

server.start({ transportType: "stdio" });
```

Note: FastMCP does not support MCP elicitation. Steps with `source: elicit` captures will fall back to agent-driven collection.

### Official @modelcontextprotocol/sdk

```typescript
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { OfficialSdkAdapter } from "vela-sdk/adapters/mcp-sdk";

const mcpServer = new McpServer(
  { name: "my-server", version: "1.0.0" },
  { capabilities: {} },
);
const adapter = new OfficialSdkAdapter(mcpServer);

const workflows = new VelaWorkflows({
  server: adapter,
  workflows: [yaml],
});
```

This adapter supports full MCP elicitation for interactive capture collection.

## API Reference

### Main

| Export | Type | Description |
|---|---|---|
| `VelaWorkflows` | class | Main entry point -- parses YAML, registers tools/prompts |
| `VelaWorkflowsOptions` | interface | Constructor options |

### Engine

| Export | Type | Description |
|---|---|---|
| `DefaultWorkflowEngine` | class | Built-in state machine engine |
| `IWorkflowEngine` | interface | Engine protocol for custom implementations |
| `PromptBuilder` | class | Assembles step prompts with template resolution |
| `DialogModeRegistry` | class | Registry for dialog step modes |
| `WorkflowRunState` | interface | Runtime state of a workflow run |
| `WorkflowRunStatus` | enum | `active`, `paused`, `completed`, `cancelled` |
| `AdvanceResult` | interface | Return value of `engine.advance()` |

### Storage

| Export | Type | Description |
|---|---|---|
| `WorkflowStore` | interface | Storage protocol |
| `InMemoryStore` | class | In-memory store (default) |
| `LocalStorageStore` | class | KV-backed persistent store |
| `KVStorage` | interface | Minimal KV interface (`getItem`/`setItem`/`removeItem`) |

### MCP

| Export | Type | Description |
|---|---|---|
| `McpServerAdapter` | interface | Framework-agnostic server interface |
| `McpContext` | interface | Tool execution context (elicit + log) |
| `FastMcpAdapter` | class | Adapter for `fastmcp` (import from `vela-sdk/adapters/fastmcp`) |
| `OfficialSdkAdapter` | class | Adapter for `@modelcontextprotocol/sdk` (import from `vela-sdk/adapters/mcp-sdk`) |

### Protocols

| Export | Type | Description |
|---|---|---|
| `WorkflowResolver` | interface | Resolve workflow definitions from any source |
| `SessionProvider` | interface | Provide scoped `WorkflowStore` sessions |
| `ParamFilter` | interface | Control missing-param elicitation |
| `ProjectResolver` | interface | Resolve project slugs to IDs |

### Schemas & Loader

| Export | Type | Description |
|---|---|---|
| `WorkflowDefinition` | interface | Parsed workflow definition |
| `ToolRequirement` | interface | External MCP tool declaration (name, server, description, required) |
| `AgentDefinition` | interface | Parsed agent definition |
| `parseWorkflowYaml` | function | Parse YAML string to `WorkflowDefinition` |
| `parseAgentYaml` | function | Parse YAML string to `AgentDefinition` |

### Locale

| Export | Type | Description |
|---|---|---|
| `Locale` | interface | All user-facing strings |
| `getLocale` | function | Get built-in locale (`"en"` or `"de"`) |
| `enLocale` / `deLocale` | function | Locale factory functions |

## License

MIT
