/**
 * Extension protocols for vela-sdk MCP integration.
 *
 * Defines pluggable interfaces so MCP servers can inject custom logic
 * for workflow resolution, session management, parameter filtering, and
 * project resolution.
 */

import type {
  ParamDefinition,
  WorkflowDefinition,
} from "../schemas/workflow.js";
import type { WorkflowStore } from "../storage/store.js";

// ---------------------------------------------------------------------------
// WorkflowResolver
// ---------------------------------------------------------------------------

export interface WorkflowResolver {
  getWorkflow(
    workflowId: string,
    version?: string | null,
  ): Promise<WorkflowDefinition | null>;

  listWorkflows(): Promise<Record<string, WorkflowDefinition>>;
}

// ---------------------------------------------------------------------------
// SessionProvider
// ---------------------------------------------------------------------------

/**
 * Provides WorkflowStore instances with proper lifecycle management.
 *
 * The returned object must support `Symbol.asyncDispose` or a manual
 * dispose pattern. For convenience the default implementation uses a
 * simple async-generator based approach.
 */
export interface SessionProvider {
  session(): AsyncSession;
}

/** An async-disposable wrapper around a WorkflowStore. */
export interface AsyncSession {
  store: WorkflowStore;
  close(): Promise<void>;
}

// ---------------------------------------------------------------------------
// ParamFilter
// ---------------------------------------------------------------------------

export interface ParamFilter {
  filterMissingParams(
    wfDef: WorkflowDefinition,
    providedParams: Record<string, unknown>,
  ): ParamDefinition[];
}

// ---------------------------------------------------------------------------
// ProjectResolver
// ---------------------------------------------------------------------------

export interface ProjectResolver {
  resolveProjectId(projectSlug?: string | null): Promise<string | null>;
}

// ---------------------------------------------------------------------------
// Default implementations
// ---------------------------------------------------------------------------

/**
 * Wraps a `Record<string, WorkflowDefinition>` to satisfy WorkflowResolver.
 */
export class InMemoryWorkflowResolver implements WorkflowResolver {
  private readonly workflows: Record<string, WorkflowDefinition>;

  constructor(workflows: Record<string, WorkflowDefinition>) {
    this.workflows = { ...workflows };
  }

  async getWorkflow(
    workflowId: string,
    version?: string | null,
  ): Promise<WorkflowDefinition | null> {
    if (version) {
      const key = `${workflowId}@${version}`;
      return this.workflows[key] ?? null;
    }
    const matches = Object.values(this.workflows).filter(
      (wf) => wf.id === workflowId,
    );
    if (matches.length === 0) {
      return null;
    }
    matches.sort((a, b) => (a.version < b.version ? 1 : -1));
    return matches[0];
  }

  async listWorkflows(): Promise<Record<string, WorkflowDefinition>> {
    return { ...this.workflows };
  }
}

/**
 * Wraps a single WorkflowStore, returning it as an async session.
 */
export class SimpleSessionProvider implements SessionProvider {
  private readonly store: WorkflowStore;

  constructor(store: WorkflowStore) {
    this.store = store;
  }

  session(): AsyncSession {
    const store = this.store;
    return {
      store,
      async close() {
        // No-op for in-memory stores
      },
    };
  }
}

/**
 * Returns required params that are missing from provided params.
 */
export class DefaultParamFilter implements ParamFilter {
  filterMissingParams(
    wfDef: WorkflowDefinition,
    providedParams: Record<string, unknown>,
  ): ParamDefinition[] {
    return wfDef.params.filter(
      (p) => p.required && !(p.name in providedParams),
    );
  }
}
