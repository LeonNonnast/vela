/**
 * Headless MCP server adapter.
 *
 * A no-op adapter that collects tools and prompts without exposing them
 * on an MCP server. Use this when you want VelaWorkflows' prompt building,
 * elicitation, and workflow engine — but don't need HTTP/stdio MCP transport.
 *
 * Tools and prompts are stored internally and can be retrieved via
 * `getTools()` and `getPrompts()` for custom bridging (e.g. into an
 * Agent SDK MCP server or Electron IPC).
 */

import type {
  McpServerAdapter,
  McpToolDefinition,
  McpPromptDefinition,
} from "../mcp/mcp-server.js";

export class HeadlessAdapter implements McpServerAdapter {
  private tools = new Map<string, McpToolDefinition>();
  private prompts = new Map<string, McpPromptDefinition>();

  addTool(tool: McpToolDefinition): void {
    this.tools.set(tool.name, tool);
  }

  addPrompt(prompt: McpPromptDefinition): void {
    this.prompts.set(prompt.name, prompt);
  }

  /** Get all registered tool definitions. */
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
}
