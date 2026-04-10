/**
 * LangChain adapter — bridges the vela-sdk McpServerAdapter interface
 * to LangChain.js `StructuredTool` instances.
 *
 * Import from `vela-sdk/adapters/langchain`.
 *
 * @example
 * ```ts
 * import { createVelaToolkit } from "vela-sdk/adapters/langchain";
 *
 * const { tools } = createVelaToolkit({
 *   workflows: [myWorkflowYaml],
 * });
 *
 * // Use with any LangChain agent
 * const agent = createReactAgent({ llm, tools });
 * ```
 */

import { DynamicStructuredTool } from "@langchain/core/tools";
import { z } from "zod";
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
// JSON Schema → Zod conversion
// ---------------------------------------------------------------------------

interface JsonSchemaProperty {
  type?: string;
  description?: string;
  enum?: string[];
}

/**
 * Converts a flat JSON Schema object to a Zod object schema.
 *
 * Handles the simple case used by Vela tools: all properties are strings,
 * some required, some optional.
 */
function jsonSchemaToZod(
  jsonSchema: Record<string, unknown>,
): z.ZodObject<Record<string, z.ZodTypeAny>> {
  const properties = (jsonSchema.properties ?? {}) as Record<
    string,
    JsonSchemaProperty
  >;
  const required = new Set(
    (jsonSchema.required ?? []) as string[],
  );

  const shape: Record<string, z.ZodTypeAny> = {};
  for (const [key, prop] of Object.entries(properties)) {
    let field: z.ZodTypeAny = z
      .string()
      .describe(prop.description ?? "");
    if (!required.has(key)) {
      field = field.optional();
    }
    shape[key] = field;
  }
  return z.object(shape);
}

// ---------------------------------------------------------------------------
// No-op McpContext for LangChain
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
      // LangChain has no elicitation primitive — decline gracefully so the
      // workflow engine falls back to agent-driven parameter collection.
      return { action: "decline" };
    },
  };
}

// ---------------------------------------------------------------------------
// LangChainAdapter
// ---------------------------------------------------------------------------

export class LangChainAdapter implements McpServerAdapter {
  private readonly tools = new Map<string, McpToolDefinition>();
  private readonly langchainTools = new Map<string, DynamicStructuredTool>();
  private readonly prompts = new Map<string, McpPromptDefinition>();
  private readonly ctx: McpContext;

  constructor(ctx?: McpContext) {
    this.ctx = ctx ?? createNoOpContext();
  }

  addTool(tool: McpToolDefinition): void {
    this.tools.set(tool.name, tool);

    const schema = jsonSchemaToZod(tool.parameters);
    const ctx = this.ctx;

    const lcTool = new DynamicStructuredTool({
      name: tool.name,
      description: tool.description,
      schema,
      async func(
        args: Record<string, unknown>,
      ): Promise<string> {
        return tool.execute(args, ctx);
      },
    });

    this.langchainTools.set(tool.name, lcTool);
  }

  addPrompt(prompt: McpPromptDefinition): void {
    this.prompts.set(prompt.name, prompt);
  }

  /** Get all registered tools as LangChain StructuredTool instances. */
  getTools(): DynamicStructuredTool[] {
    return Array.from(this.langchainTools.values());
  }

  /** Get a LangChain tool by name. */
  getTool(name: string): DynamicStructuredTool | undefined {
    return this.langchainTools.get(name);
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

  /** Load a prompt's content (e.g. for injection into a system message). */
  async loadPrompt(name: string): Promise<string | undefined> {
    const prompt = this.prompts.get(name);
    if (!prompt) return undefined;
    return prompt.load(this.ctx);
  }
}

// ---------------------------------------------------------------------------
// Convenience factory
// ---------------------------------------------------------------------------

export interface VelaToolkitResult {
  /** LangChain tools ready for use with any agent. */
  tools: DynamicStructuredTool[];
  /** The underlying VelaWorkflows instance. */
  vela: VelaWorkflows;
  /** The adapter — use for prompt access and advanced use cases. */
  adapter: LangChainAdapter;
}

/**
 * Create a Vela toolkit for LangChain agents.
 *
 * @example
 * ```ts
 * import { createVelaToolkit } from "vela-sdk/adapters/langchain";
 *
 * const { tools } = createVelaToolkit({
 *   workflows: [myWorkflowYaml],
 * });
 * ```
 */
export function createVelaToolkit(
  options: Omit<VelaWorkflowsOptions, "server">,
): VelaToolkitResult {
  const adapter = new LangChainAdapter();
  const vela = new VelaWorkflows({ ...options, server: adapter });
  return { tools: adapter.getTools(), vela, adapter };
}
