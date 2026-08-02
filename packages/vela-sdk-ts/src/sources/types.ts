/**
 * Source registry — generic named-callback handlers for `mcp_call` steps
 * and the `fetch` step field.
 *
 * Both schema features describe the same idea: "call a mounted MCP source
 * by name". Neither engine has a real MCP client, so this mirrors the
 * `delegate` registry pattern (../delegate/types.ts) instead: the embedding
 * app registers a handler per source namespace (e.g. "devops"), and the
 * engine looks it up and invokes it in-process.
 */

/** Context passed to a source handler when it is invoked. */
export interface SourceContext {
  /** Cancellation signal propagated from the workflow run. */
  signal?: AbortSignal;

  /** Structured log hook (forwarded to the MCP context if available). */
  log: (msg: string, meta?: unknown) => void;
}

/**
 * Source-handler signature. `tool` is the action/tool name being called
 * (`mcp_call.mcp_tool` or `fetch.action`); `params` has already had
 * `{{...}}` templates resolved by the engine. Must return a
 * JSON-serialisable result.
 */
export type SourceHandler = (
  tool: string,
  params: Record<string, unknown>,
  ctx: SourceContext,
) => Promise<unknown>;
