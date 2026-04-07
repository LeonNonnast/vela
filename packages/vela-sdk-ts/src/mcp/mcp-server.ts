/**
 * MCP server abstraction layer.
 *
 * Defines framework-agnostic interfaces for MCP server adapters,
 * tools, prompts, and the elicitation context.
 */

// ---------------------------------------------------------------------------
// ElicitResult
// ---------------------------------------------------------------------------

export interface ElicitResult {
  action: "accept" | "decline" | "cancel";
  content?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// McpContext
// ---------------------------------------------------------------------------

export interface McpContext {
  elicit(
    message: string,
    schema: Record<string, unknown>,
  ): Promise<ElicitResult>;

  log: {
    debug(msg: string, data?: unknown): void;
    info(msg: string, data?: unknown): void;
    warn(msg: string, data?: unknown): void;
    error(msg: string, data?: unknown): void;
  };
}

// ---------------------------------------------------------------------------
// McpToolDefinition / McpPromptDefinition
// ---------------------------------------------------------------------------

export interface McpToolDefinition {
  name: string;
  description: string;
  parameters: Record<string, unknown>; // JSON Schema
  execute: (
    args: Record<string, unknown>,
    ctx: McpContext,
  ) => Promise<string>;
}

export interface McpPromptDefinition {
  name: string;
  description: string;
  load: (ctx: McpContext) => Promise<string>;
}

// ---------------------------------------------------------------------------
// McpServerAdapter
// ---------------------------------------------------------------------------

export interface McpServerAdapter {
  addTool(tool: McpToolDefinition): void;
  addPrompt(prompt: McpPromptDefinition): void;
}
