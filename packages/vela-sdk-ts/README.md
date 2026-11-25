# vela-sdk

TypeScript workflow engine for MCP servers.

Add structured, multi-step workflows to any MCP server. Define workflows in YAML; vela-sdk registers the tools and prompts, drives the state machine, persists run state, and handles elicitation dialogs automatically.

## Installation

```bash
npm install vela-sdk
```

Plus the framework you integrate with (all optional peer dependencies):

```bash
npm install @modelcontextprotocol/sdk   # official MCP SDK (full elicitation support)
npm install fastmcp                     # FastMCP
npm install @langchain/core             # LangChain.js
```

Requires Node.js >= 20. Ships ESM and CommonJS builds with type definitions.

## Quick Start

```typescript
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { VelaWorkflows } from "vela-sdk";
import { OfficialSdkAdapter } from "vela-sdk/adapters/mcp-sdk";

const mcpServer = new McpServer(
  { name: "my-server", version: "1.0.0" },
  { capabilities: {} },
);

new VelaWorkflows({
  server: new OfficialSdkAdapter(mcpServer),
  workflows: [myWorkflowYaml], // YAML strings
  agents: [myAgentYaml],       // optional
});

await mcpServer.connect(new StdioServerTransport());
```

The constructor parses the YAML and registers:

| Tool | Purpose |
|---|---|
| `workflow_advance` | Start/resume a run (`workflow_id`, `params` as JSON string) or advance it (`run_id`, `output`, optional `notes`, `step_id`) |
| `workflow_status` | Show the state of a run |
| `workflow_list` | List available workflows and active runs |

Plus one MCP prompt per workflow (`workflow_<id>`) and one per agent (`agent_<id>`). Every tool response contains a `next_action` telling the agent exactly what to do next.

## Workflow YAML

```yaml
id: onboarding
version: "1.0.0"
name: Employee Onboarding
description: Onboard a new team member
params:
  - name: employee_name
    label: Employee Name
    required: true
    identity: true          # same identity → resume the existing run
lifecycle:
  allow_pause: true
  auto_cancel_after: "30d"
  auto_archive_after: "90d"
steps:
  - id: collect_info
    type: freeform
    name: Collect Information
    prompt: "Please provide the department and start date for {{params.employee_name}}."
    capture:
      - key: department
        label: Department
        source: elicit
        required: true
      - key: start_date
        label: Start Date
        source: elicit
        required: true
  - id: setup_accounts
    type: execute
    name: Set Up Accounts
    depends_on:
      - step: collect_info
        fields: [department]
    prompt: "Create accounts for {{params.employee_name}} in {{state.department}}."
  - id: confirm_complete
    type: confirm
    name: Confirm Completion
    prompt: "All accounts created. Confirm onboarding is complete."
```

### Step types

| Type | Purpose | Specific fields |
|---|---|---|
| `freeform` | Free-text answer | – |
| `choice` | Pick one option, optionally branching | `options[]` (`key`, `label`, `description`, `next`) |
| `confirm` | Yes/no confirmation | – |
| `execute` | Agent performs a task | `instructions`, `delegate` |
| `dialog` | Guided conversation in phases | `mode` (`brainstorming`, `requirements`, `planning`, `review`, `freeform`), `goal`, `guidelines`, `phases` |
| `workflow` | Run a sub-workflow; parent resumes automatically when it completes | `workflow_ref`, `params_mapping` |
| `mcp_call` | Server-side tool call via a registered source, auto-advances | `mcp_source`, `mcp_tool`, `mcp_params` |
| `delegate` | Hand execution to a registered in-process handler, auto-advances | `delegate`, `task` |

### Fields available on every step

| Field | Purpose |
|---|---|
| `prompt` | Prompt text, supports templates |
| `capture[]` | Values to store in run state: `key`, `label`, `type`, `required`, `source` (`output` or `elicit`), `elicit` (`if_missing`, `never`, …), `options`, `default`, `placeholder` |
| `next` | Explicit next step id |
| `depends_on[]` | Required fields from earlier steps (`step`, `fields`); the run is blocked until they exist |
| `fetch[]` | Data loaded via a registered source before the step is shown (`key`, `source`, `action`, `params`) |
| `tools[]` | External MCP tools the step needs |
| `on_error` | `retry`, `fallback`, `abort`, `message` |
| `resources[]` | Resource definitions appended to the prompt |
| `notes` | Allow agent notes (default `true`) |

### Templates

| Syntax | Resolves to |
|---|---|
| `{{params.x}}` | Workflow parameter |
| `{{state.x}}` | Captured value |
| `{{steps.<step_id>.<key>}}` | Captured value, scoped to the step that captured it |
| `{{resolved.x}}` | Params flagged `resolve: true` |
| `{{fetch.x}}` | Result of the current step's `fetch` |
| `{{project.x}}` | Project data from a `ProjectDataResolver` (engine option) |

### Workflow-level fields

`id`, `version`, `name`, `description`, `params[]` (`name`, `label`, `description`, `required`, `default`, `identity`, `resolve`), `lifecycle` (`allow_pause`, `auto_cancel_after`, `auto_archive_after` — durations like `"48h"`, `"30d"`), `tools[]` (`name`, `server`, `description`, `required`), `resources[]`, `steps[]`.

### Agent personas

```yaml
id: hr-assistant
name: HR Assistant
persona: You are a helpful HR assistant that guides managers through employee workflows.
greeting: Hello! I can help you with onboarding, offboarding, and other HR workflows.
workflows:
  - onboarding
  - offboarding
```

Agents register as MCP prompts (`agent_<id>`).

## Server-side execution: sources and delegates

`mcp_call` steps and `fetch` call a **source** — a handler you register per namespace:

```typescript
import { registerSource } from "vela-sdk";

registerSource("devops", async (tool, params, ctx) => {
  // tool = mcp_call.mcp_tool or fetch.action; params already template-resolved
  return await myDevOpsClient.call(tool, params);
});
```

```yaml
- id: load_ticket
  type: mcp_call
  mcp_source: devops
  mcp_tool: get_work_item
  mcp_params: { id: "{{params.ticket_id}}" }
  capture:
    - key: ticket
  on_error: { retry: 2, fallback: manual_entry }
```

`delegate` steps call a **delegate handler**:

```typescript
import { registerDelegate } from "vela-sdk";

registerDelegate("shell", async (step, ctx) => {
  const cmd = ctx.resolveVars(step.task);
  const out = await runCommand(cmd);
  ctx.setCapture("exit_code", out.code);
  return out.stdout;
});
```

```yaml
- id: build
  type: delegate
  delegate: shell
  task: "npm run build"
```

Registering the same name twice throws. Failures go through the step's `on_error` (retry, fallback, abort).

## Adapters

| Adapter | Import | Notes |
|---|---|---|
| `OfficialSdkAdapter` | `vela-sdk/adapters/mcp-sdk` | Full MCP elicitation support |
| `FastMcpAdapter` | `vela-sdk/adapters/fastmcp` | No elicitation; `source: elicit` captures fall back to agent-driven collection |
| `createVelaToolkit` / `LangChainAdapter` | `vela-sdk/adapters/langchain` | Returns LangChain `StructuredTool`s |
| `createVelaAzureToolset` / `AzureAgentsAdapter` | `vela-sdk/adapters/azure-agents` (also root export) | Azure AI Agents function tools + `handleToolCall` |
| `HeadlessAdapter` | `vela-sdk` | No transport; collects tools/prompts for custom bridging (IPC, Agent SDK, UI). Default when `server` is omitted |

```typescript
// FastMCP
import { FastMCP } from "fastmcp";
import { FastMcpAdapter } from "vela-sdk/adapters/fastmcp";
const server = new FastMCP({ name: "my-server", version: "1.0.0" });
new VelaWorkflows({ server: new FastMcpAdapter(server), workflows: [yaml] });
server.start({ transportType: "stdio" });

// LangChain
import { createVelaToolkit } from "vela-sdk/adapters/langchain";
const { tools } = createVelaToolkit({ workflows: [yaml] });

// Azure AI Agents
import { createVelaAzureToolset } from "vela-sdk/adapters/azure-agents";
const { tools, handleToolCall } = createVelaAzureToolset({ workflows: [yaml] });
```

## Configuration

```typescript
new VelaWorkflows({
  server,                     // McpServerAdapter (default: HeadlessAdapter)
  workflows: [yaml],          // workflow YAML strings
  agents: [yaml],             // agent YAML strings
  resources: [yaml],          // resource YAML strings
  store,                      // WorkflowStore (default: InMemoryStore)
  engine,                     // IWorkflowEngine (default: DefaultWorkflowEngine)
  locale: getLocale("de"),    // "en" (default) or "de", or a custom Locale
  autoAdvance: true,          // run agent-driven steps without a round-trip
  registerPrompts: true,
  toolPrefix: "workflow",     // → workflow_advance, workflow_status, workflow_list
  toolNameFormat: { advance: "do_step" },
  resourceResolver,           // resolve resource references
  workflowResolver,           // load workflows from a DB/API
  sessionProvider,            // per-request WorkflowStore (e.g. transactions)
  paramFilter,                // control which missing params get elicited
  projectResolver,            // resolve project slugs to ids
});
```

### Storage

`InMemoryStore` (default) loses state on restart. `LocalStorageStore` persists to any KV backend with `getItem`/`setItem`/`removeItem` (sync or async):

```typescript
import { LocalStorageStore } from "vela-sdk";
const store = new LocalStorageStore(myRedisAdapter, "myapp:");
```

Or implement `WorkflowStore` yourself:

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

### Custom engine

Implement `IWorkflowEngine` (`startOrResume`, `advance`, `assemblePrompt`, `getStep`, `checkLifecycle`, `validateDependsOn`, `handleOnError`) and pass it as `engine`.

## API overview

| Area | Exports |
|---|---|
| Main | `VelaWorkflows`, `VelaWorkflowsOptions` |
| Engine | `DefaultWorkflowEngine`, `IWorkflowEngine`, `PromptBuilder`, `DialogModeRegistry`, `WorkflowRunState`, `WorkflowRunStatus`, `AdvanceResult`, `ResourceResolver`, `ProjectDataResolver` |
| Sources / delegates | `registerSource`, `resolveSource`, `clearSources`, `registerDelegate`, `resolveDelegate`, `clearDelegates`, `makeDelegateStep` |
| Storage | `WorkflowStore`, `InMemoryStore`, `LocalStorageStore`, `KVStorage` |
| MCP | `McpServerAdapter`, `McpContext`, `HeadlessAdapter`, `AzureAgentsAdapter`, `createVelaAzureToolset`, `ElicitationService`, response/elicitation helpers |
| Protocols | `WorkflowResolver`, `SessionProvider`, `ParamFilter`, `ProjectResolver`, `InMemoryWorkflowResolver`, `SimpleSessionProvider`, `DefaultParamFilter` |
| Schemas & loader | Zod schemas (`workflowDefinitionSchema`, `anyStepSchema`, …), `parseWorkflowYaml`, `parseAgentYaml`, `parseResourceYaml`, `parseWorkflowFilename` |
| Locale | `Locale`, `getLocale`, `enLocale`, `deLocale` |

## License

MIT
