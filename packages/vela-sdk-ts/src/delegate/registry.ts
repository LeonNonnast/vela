/**
 * Global delegate-handler registry.
 *
 * Module-level Map; lookups are O(1). Re-registering the same name throws
 * to surface duplicate-bootstrap bugs early. `clearDelegates()` is exported
 * for tests only.
 */

import type { DelegateHandler } from "./types.js";

const handlers = new Map<string, DelegateHandler>();

/**
 * Register a handler for a delegate name (e.g. "engine", "shell").
 *
 * @throws if the name is already registered.
 */
export function registerDelegate(name: string, handler: DelegateHandler): void {
  if (handlers.has(name)) {
    throw new Error(`delegate '${name}' already registered`);
  }
  handlers.set(name, handler);
}

/** Look up a registered handler. Returns undefined if not registered. */
export function resolveDelegate(name: string): DelegateHandler | undefined {
  return handlers.get(name);
}

/** Test utility — wipes the registry so suites stay isolated. */
export function clearDelegates(): void {
  handlers.clear();
}
