/**
 * Azure AI Agents adapter — bridges the vela-sdk McpServerAdapter interface
 * to Azure AI Foundry Agents native function tool definitions.
 *
 * Azure AI Agents does not support MCP natively, so this adapter converts
 * Vela MCP tools into Azure-compatible function tool definitions and provides
 * a dispatch method for handling tool calls.
 *
 * Import from `vela-sdk/adapters/azure-agents`.
 *
 * @example
 * ```ts
 * import { createVelaAzureToolset } from "vela-sdk/adapters/azure-agents";
 *
 * const { tools, handleToolCall, promptAdvisor } = createVelaAzureToolset({
 *   workflows: [myWorkflowYaml],
 * });
 *
 * // Pass `tools` to your Azure AI Agent as function tool definitions
 * // Use `handleToolCall` to dispatch tool invocations from the agent
 * // Inject `promptAdvisor` into the agent's system instructions
 * ```
 */

import type {
  McpServerAdapter,
  McpToolDefinition,
  McpPromptDefinition,
  McpContext,
  ElicitResult,
} from "../mcp/mcp-server.js";
import { VelaWorkflows } from "../vela-workflows.js";
import type { VelaWorkflowsOptions } from "../vela-workflows.js";

// ---------------------------------------------------------------------------
// Azure function tool definition types
// ---------------------------------------------------------------------------

export interface AzureFunctionToolDefinition {
  type: "function";
  function: {
    name: string;
    description: string;
    parameters: {
      type: "object";
      properties: Record<string, { type: string; description: string }>;
      required?: string[];
    };
  };
}

// ---------------------------------------------------------------------------
// No-op McpContext for Azure AI Agents
// ---------------------------------------------------------------------------

function createNoOpContext(): McpContext {
  return {
    log: {
      debug() {},
      info() {},
      warn() {},
      error() {},
    },
    async elicit(
      _message: string,
      _schema: Record<string, unknown>,
    ): Promise<ElicitResult> {
      // Azure AI Agents has no elicitation primitive — decline gracefully so the
      // workflow engine falls back to agent-driven parameter collection.
      return { action: "decline" };
    },
  };
}

// ---------------------------------------------------------------------------
// AzureAgentsAdapter
// ---------------------------------------------------------------------------

export class AzureAgentsAdapter implements McpServerAdapter {
  private readonly tools = new Map<string, McpToolDefinition>();
  private readonly prompts = new Map<string, McpPromptDefinition>();
  private readonly ctx: McpContext;

  constructor(ctx?: McpContext) {
    this.ctx = ctx ?? createNoOpContext();
  }

  addTool(tool: McpToolDefinition): void {
    this.tools.set(tool.name, tool);
  }

  addPrompt(prompt: McpPromptDefinition): void {
    this.prompts.set(prompt.name, prompt);
  }

  /**
   * Get all registered tools as Azure function tool definitions.
   *
   * Each definition follows the Azure AI Agents function tool schema:
   * `{ type: "function", function: { name, description, parameters } }`.
   */
  getToolDefinitions(): AzureFunctionToolDefinition[] {
    return Array.from(this.tools.values()).map((tool) =>
      mcpToolToAzureDefinition(tool),
    );
  }

  /**
   * Dispatch a tool call by name, executing the underlying MCP tool handler.
   *
   * @returns The tool result as a JSON string.
   */
  async handleToolCall(
    name: string,
    args: Record<string, unknown>,
  ): Promise<string> {
    const tool = this.tools.get(name);
    if (!tool) {
      return JSON.stringify({ error: "Unknown tool", tool_name: name });
    }
    return tool.execute(args, this.ctx);
  }

  /**
   * Build a prompt advisor string describing available workflows
   * and how to use the registered tools.
   */
  getPromptAdvisor(): string {
    const parts: string[] = [];

    parts.push("# Vela Workflow Tools");
    parts.push("");
    parts.push(
      "You have access to workflow tools that let you start, advance, " +
        "and monitor structured workflows. Follow the instructions returned " +
        "by each tool call — execute the `next_action` immediately without " +
        "asking the user for permission.",
    );
    parts.push("");

    // List available tools
    parts.push("## Available Tools");
    for (const tool of this.tools.values()) {
      parts.push(`- **${tool.name}**: ${tool.description}`);
    }
    parts.push("");

    // List available workflow prompts
    if (this.prompts.size > 0) {
      parts.push("## Available Workflows");
      for (const prompt of this.prompts.values()) {
        parts.push(`- **${prompt.name}**: ${prompt.description}`);
      }
      parts.push("");
    }

    return parts.join("\n");
  }

  /** Get all registered MCP tool definitions. */
  getTools(): McpToolDefinition[] {
    return Array.from(this.tools.values());
  }

  /** Get a tool by name. */
  getTool(name: string): McpToolDefinition | undefined {
    return this.tools.get(name);
  }

  /** Get all registered prompt definitions. */
  getPrompts(): McpPromptDefinition[] {
    return Array.from(this.prompts.values());
  }

  /** Get a prompt by name. */
  getPrompt(name: string): McpPromptDefinition | undefined {
    return this.prompts.get(name);
  }

  /** List prompt names and descriptions. */
  listPrompts(): Array<{ name: string; description: string }> {
    return Array.from(this.prompts.values()).map((p) => ({
      name: p.name,
      description: p.description,
    }));
  }

  /** Load a prompt's content. */
  async loadPrompt(name: string): Promise<string | undefined> {
    const prompt = this.prompts.get(name);
    if (!prompt) return undefined;
    return prompt.load(this.ctx);
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface JsonSchemaProperty {
  type?: string;
  description?: string;
}

/**
 * Convert an MCP tool definition to an Azure function tool definition.
 */
function mcpToolToAzureDefinition(
  tool: McpToolDefinition,
): AzureFunctionToolDefinition {
  const jsonSchema = tool.parameters;
  const properties = (jsonSchema.properties ?? {}) as Record<
    string,
    JsonSchemaProperty
  >;
  const required = (jsonSchema.required ?? []) as string[];

  const azureProperties: Record<string, { type: string; description: string }> =
    {};
  for (const [key, prop] of Object.entries(properties)) {
    azureProperties[key] = {
      type: prop.type ?? "string",
      description: prop.description ?? "",
    };
  }

  const def: AzureFunctionToolDefinition = {
    type: "function",
    function: {
      name: tool.name,
      description: tool.description,
      parameters: {
        type: "object",
        properties: azureProperties,
      },
    },
  };

  if (required.length > 0) {
    def.function.parameters.required = required;
  }

  return def;
}

// ---------------------------------------------------------------------------
// Convenience factory
// ---------------------------------------------------------------------------

export interface VelaAzureToolsetResult {
  /** Azure function tool definitions ready for use with Azure AI Agents. */
  tools: AzureFunctionToolDefinition[];
  /** Dispatch a tool call by name. Returns the result as a JSON string. */
  handleToolCall: (
    name: string,
    args: Record<string, unknown>,
  ) => Promise<string>;
  /** Prompt advisor text describing available workflows and tool usage. */
  promptAdvisor: string;
  /** The underlying VelaWorkflows instance. */
  vela: VelaWorkflows;
  /** The adapter — use for prompt access and advanced use cases. */
  adapter: AzureAgentsAdapter;
}

/**
 * Create a Vela toolset for Azure AI Agents.
 *
 * @example
 * ```ts
 * import { createVelaAzureToolset } from "vela-sdk/adapters/azure-agents";
 *
 * const { tools, handleToolCall, promptAdvisor } = createVelaAzureToolset({
 *   workflows: [myWorkflowYaml],
 * });
 * ```
 */
export function createVelaAzureToolset(
  options: Omit<VelaWorkflowsOptions, "server">,
): VelaAzureToolsetResult {
  const adapter = new AzureAgentsAdapter();
  const vela = new VelaWorkflows({ ...options, server: adapter });
  return {
    tools: adapter.getToolDefinitions(),
    handleToolCall: (name, args) => adapter.handleToolCall(name, args),
    promptAdvisor: adapter.getPromptAdvisor(),
    vela,
    adapter,
  };
}
