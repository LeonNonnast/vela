/**
 * Official `@modelcontextprotocol/sdk` adapter — bridges the vela-sdk
 * McpServerAdapter interface to the official MCP TypeScript SDK.
 *
 * Import from `vela-sdk/adapters/mcp-sdk`.
 *
 * @example
 * ```ts
 * import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
 * import { OfficialSdkAdapter } from "vela-sdk/adapters/mcp-sdk";
 *
 * const mcpServer = new McpServer(
 *   { name: "my-server", version: "1.0.0" },
 *   { capabilities: {} },
 * );
 * const adapter = new OfficialSdkAdapter(mcpServer);
 * registerVelaTools(adapter);   // uses McpServerAdapter
 * ```
 */

import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { Server } from "@modelcontextprotocol/sdk/server/index.js";
import type {
  McpServerAdapter,
  McpToolDefinition,
  McpPromptDefinition,
  McpContext,
  ElicitResult,
} from "../mcp/mcp-server.js";

// ---------------------------------------------------------------------------
// Context mapping
// ---------------------------------------------------------------------------

/**
 * Build an `McpContext` from the official SDK's underlying `Server` instance.
 *
 * The official SDK supports elicitation through `server.elicitInput`.
 */
function buildMcpContext(server: Server): McpContext {
  return {
    log: {
      debug: (msg: string) =>
        server
          .sendLoggingMessage({ level: "debug", data: msg, logger: "vela" })
          .catch(() => {}),
      info: (msg: string) =>
        server
          .sendLoggingMessage({ level: "info", data: msg, logger: "vela" })
          .catch(() => {}),
      warn: (msg: string) =>
        server
          .sendLoggingMessage({ level: "warning", data: msg, logger: "vela" })
          .catch(() => {}),
      error: (msg: string) =>
        server
          .sendLoggingMessage({ level: "error", data: msg, logger: "vela" })
          .catch(() => {}),
    },

    async elicit(
      message: string,
      schema: Record<string, unknown>,
    ): Promise<ElicitResult> {
      // The official SDK's `Server.elicitInput` expects form params with a
      // JSON Schema `requestedSchema`.  We map our generic interface onto it.
      try {
        const result = await server.elicitInput({
          mode: "form" as const,
          message,
          requestedSchema: schema,
        } as Parameters<Server["elicitInput"]>[0]);

        return {
          action: result.action as ElicitResult["action"],
          content: result.content as Record<string, unknown> | undefined,
        };
      } catch (err: unknown) {
        // If elicitation is not supported by the client, return a decline.
        const errMessage =
          err instanceof Error ? err.message : String(err);
        if (
          errMessage.includes("not supported") ||
          errMessage.includes("capability")
        ) {
          return { action: "decline" };
        }
        throw err;
      }
    },
  };
}

// ---------------------------------------------------------------------------
// Adapter
// ---------------------------------------------------------------------------

export class OfficialSdkAdapter implements McpServerAdapter {
  constructor(private readonly mcpServer: McpServer) {}

  addTool(tool: McpToolDefinition): void {
    // Register with the high-level McpServer API.
    // We omit inputSchema — the SDK will accept any arguments.
    // Actual validation is handled by the workflow engine.
    // The tool description communicates the parameter contract to the LLM.
    const mcpServer = this.mcpServer;

    mcpServer.registerTool(
      tool.name,
      {
        description: tool.description,
      },
      async (extra) => {
        const ctx = buildMcpContext(mcpServer.server);

        // When no inputSchema is provided, the SDK passes the raw args
        // as the first argument (which is actually `extra`).  We need to
        // retrieve the arguments from the request handler context.
        // With no inputSchema, the callback signature is (extra) => Result.
        // Tool arguments are not parsed/validated by the SDK in this case.
        // The caller provides them as-is in the tool call request.
        // We use a type assertion to access them from the raw request.
        const args = ((extra as Record<string, unknown>)["_rawArgs"] ??
          {}) as Record<string, unknown>;

        const result = await tool.execute(args, ctx);

        return { content: [{ type: "text" as const, text: result }] };
      },
    );
  }

  addPrompt(prompt: McpPromptDefinition): void {
    const mcpServer = this.mcpServer;

    mcpServer.registerPrompt(
      prompt.name,
      {
        description: prompt.description,
      },
      async () => {
        const ctx = buildMcpContext(mcpServer.server);
        const text = await prompt.load(ctx);

        return {
          messages: [
            {
              role: "user" as const,
              content: { type: "text" as const, text },
            },
          ],
        };
      },
    );
  }
}
