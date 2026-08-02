/**
 * Global MCP-source-handler registry.
 *
 * Module-level Map; lookups are O(1). Re-registering the same name throws
 * to surface duplicate-bootstrap bugs early. `clearSources()` is exported
 * for tests only.
 */

import type { SourceHandler } from "./types.js";

const handlers = new Map<string, SourceHandler>();

/**
 * Register a handler for a source namespace (e.g. "devops").
 *
 * @throws if the name is already registered.
 */
export function registerSource(name: string, handler: SourceHandler): void {
  if (handlers.has(name)) {
    throw new Error(`source '${name}' already registered`);
  }
  handlers.set(name, handler);
}

/** Look up a registered handler. Returns undefined if not registered. */
export function resolveSource(name: string): SourceHandler | undefined {
  return handlers.get(name);
}

/** Test utility — wipes the registry so suites stay isolated. */
export function clearSources(): void {
  handlers.clear();
}
