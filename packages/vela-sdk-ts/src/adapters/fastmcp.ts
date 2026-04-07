/**
 * FastMCP adapter — bridges the vela-sdk McpServerAdapter interface
 * to the `fastmcp` package.
 *
 * Import from `vela-sdk/adapters/fastmcp`.
 *
 * @example
 * ```ts
 * import { FastMCP } from "fastmcp";
 * import { FastMcpAdapter } from "vela-sdk/adapters/fastmcp";
 *
 * const server = new FastMCP({ name: "my-server", version: "1.0.0" });
 * const adapter = new FastMcpAdapter(server);
 * registerVelaTools(adapter);   // uses McpServerAdapter
 * ```
 */

import type { FastMCP, FastMCPSessionAuth, Context } from "fastmcp";
import type {
  McpServerAdapter,
  McpToolDefinition,
  McpPromptDefinition,
  McpContext,
  ElicitResult,
} from "../mcp/mcp-server.js";

// ---------------------------------------------------------------------------
// JSON-Schema-to-StandardSchema shim
// ---------------------------------------------------------------------------
// FastMCP declares `ToolParameters = StandardSchemaV1` from @standard-schema/spec.
// Our interface carries plain JSON Schema objects.  We wrap the JSON Schema in
// a thin StandardSchemaV1-compatible object so that FastMCP can pass input
// through without runtime validation (validation is done elsewhere).
// ---------------------------------------------------------------------------

interface StandardSchemaShim {
  "~standard": {
    version: 1;
    vendor: string;
    validate: (value: unknown) => { value: unknown } | { issues: { message: string }[] };
  };
  [key: string]: unknown;
}

/**
 * Wraps a plain JSON Schema object into a StandardSchemaV1-compliant shim.
 *
 * The shim's `validate` always succeeds because actual argument validation is
 * the responsibility of the workflow engine, not the transport adapter.
 */
function jsonSchemaToStandardSchema(
  jsonSchema: Record<string, unknown>,
): StandardSchemaShim {
  return {
    ...jsonSchema,
    "~standard": {
      version: 1,
      vendor: "vela-sdk",
      validate(value: unknown) {
        return { value };
      },
    },
  };
}

// ---------------------------------------------------------------------------
// Context mapping
// ---------------------------------------------------------------------------

/**
 * Build an `McpContext` from the FastMCP `Context` object.
 *
 * FastMCP does not support the MCP elicitation primitive, so `ctx.elicit`
 * always throws a descriptive error.
 */
function buildMcpContext(
  fmcCtx: Context<FastMCPSessionAuth>,
): McpContext {
  return {
    log: {
      debug: (msg: string, data?: unknown) =>
        fmcCtx.log.debug(msg, data as string | undefined),
      info: (msg: string, data?: unknown) =>
        fmcCtx.log.info(msg, data as string | undefined),
      warn: (msg: string, data?: unknown) =>
        fmcCtx.log.warn(msg, data as string | undefined),
      error: (msg: string, data?: unknown) =>
        fmcCtx.log.error(msg, data as string | undefined),
    },
    async elicit(
      _message: string,
      _schema: Record<string, unknown>,
    ): Promise<ElicitResult> {
      throw new Error(
        "Elicitation is not supported by the FastMCP adapter. " +
          "Use the @modelcontextprotocol/sdk adapter (vela-sdk/adapters/mcp-sdk) " +
          "if you need elicitation capabilities.",
      );
    },
  };
}

// ---------------------------------------------------------------------------
// Adapter
// ---------------------------------------------------------------------------

export class FastMcpAdapter implements McpServerAdapter {
  constructor(private readonly server: FastMCP<FastMCPSessionAuth>) {}

  addTool(tool: McpToolDefinition): void {
    const parametersShim = jsonSchemaToStandardSchema(tool.parameters);

    this.server.addTool({
      name: tool.name,
      description: tool.description,
      parameters: parametersShim as never, // StandardSchemaV1 shim
      async execute(
        args: Record<string, unknown>,
        fmcCtx: Context<FastMCPSessionAuth>,
      ): Promise<string> {
        const ctx = buildMcpContext(fmcCtx);
        return tool.execute(args, ctx);
      },
    });
  }

  addPrompt(prompt: McpPromptDefinition): void {
    this.server.addPrompt({
      name: prompt.name,
      description: prompt.description,
      async load(): Promise<string> {
        const noopCtx: McpContext = {
          log: {
            debug() {},
            info() {},
            warn() {},
            error() {},
          },
          async elicit(): Promise<ElicitResult> {
            throw new Error(
              "Elicitation is not supported by the FastMCP adapter.",
            );
          },
        };
        return prompt.load(noopCtx);
      },
    });
  }
}
