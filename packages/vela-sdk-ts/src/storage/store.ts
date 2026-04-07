/**
 * Storage protocol for workflow runs.
 *
 * All methods are async. Implementations handle serialization
 * and persistence details internally.
 */

import type { WorkflowRunState, WorkflowRunStatus } from "../engine/types.js";

export { WorkflowRunState, WorkflowRunStatus };

/** Options for creating a new workflow run. */
export interface CreateRunOptions {
  workflowId: string;
  workflowVersion: string;
  params?: Record<string, unknown>;
  projectId?: string | null;
  parentRunId?: string | null;
  parentStepId?: string | null;
}

/** Options for updating a workflow step. */
export interface UpdateStepOptions {
  stateData?: Record<string, unknown>;
  status?: WorkflowRunStatus;
}

/** Options for listing active workflow runs. */
export interface ListActiveOptions {
  workflowId?: string;
  projectId?: string;
}

/**
 * Protocol that storage backends must implement.
 *
 * All methods return Promises. Implementations handle serialization
 * and persistence details internally.
 */
export interface WorkflowStore {
  /** Find an active/paused run matching workflowId and identity params. */
  findByIdentity(
    workflowId: string,
    identityParams: Record<string, string>,
  ): Promise<WorkflowRunState | null>;

  /** Create a new workflow run. */
  createRun(options: CreateRunOptions): Promise<WorkflowRunState>;

  /** Update the current step and optionally state/status. */
  updateStep(
    runId: string,
    stepId: string | null,
    options?: UpdateStepOptions,
  ): Promise<WorkflowRunState>;

  /** Get a workflow run by ID. */
  getById(runId: string): Promise<WorkflowRunState | null>;

  /** List active/paused workflow runs. */
  listActive(options?: ListActiveOptions): Promise<WorkflowRunState[]>;

  /** Commit pending changes. */
  commit(): Promise<void>;
}
