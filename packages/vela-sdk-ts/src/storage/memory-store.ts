/**
 * In-memory workflow store for testing and prototyping.
 *
 * Implements the WorkflowStore interface without any external dependencies.
 */

import { WorkflowRunStatus } from "../engine/types.js";
import type { WorkflowRunState } from "../engine/types.js";
import type {
  CreateRunOptions,
  ListActiveOptions,
  UpdateStepOptions,
  WorkflowStore,
} from "./store.js";

export class InMemoryStore implements WorkflowStore {
  private readonly runs = new Map<string, WorkflowRunState>();

  async findByIdentity(
    workflowId: string,
    identityParams: Record<string, string>,
  ): Promise<WorkflowRunState | null> {
    for (const run of this.runs.values()) {
      if (run.workflowId !== workflowId) continue;
      if (
        run.status !== WorkflowRunStatus.ACTIVE &&
        run.status !== WorkflowRunStatus.PAUSED
      ) {
        continue;
      }
      const allMatch = Object.entries(identityParams).every(
        ([k, v]) => run.params[k] === v,
      );
      if (allMatch) return run;
    }
    return null;
  }

  async createRun(options: CreateRunOptions): Promise<WorkflowRunState> {
    const now = new Date().toISOString();
    const run: WorkflowRunState = {
      id: crypto.randomUUID(),
      workflowId: options.workflowId,
      workflowVersion: options.workflowVersion,
      currentStep: null,
      status: WorkflowRunStatus.ACTIVE,
      params: options.params ?? {},
      stateData: {},
      projectId: options.projectId ?? null,
      parentRunId: options.parentRunId ?? null,
      parentStepId: options.parentStepId ?? null,
      startedAt: now,
      updatedAt: now,
      completedAt: null,
    };
    this.runs.set(run.id, run);
    return run;
  }

  async updateStep(
    runId: string,
    stepId: string | null,
    options?: UpdateStepOptions,
  ): Promise<WorkflowRunState> {
    const run = this.runs.get(runId);
    if (!run) {
      throw new Error(`Run not found: ${runId}`);
    }

    if (stepId !== null) {
      run.currentStep = stepId;
    }

    if (options?.stateData != null) {
      run.stateData = { ...run.stateData, ...options.stateData };
    }

    if (options?.status != null) {
      run.status = options.status;
      if (
        options.status === WorkflowRunStatus.COMPLETED ||
        options.status === WorkflowRunStatus.CANCELLED
      ) {
        run.completedAt = new Date().toISOString();
      }
    }

    run.updatedAt = new Date().toISOString();
    return run;
  }

  async getById(runId: string): Promise<WorkflowRunState | null> {
    return this.runs.get(runId) ?? null;
  }

  async listActive(options?: ListActiveOptions): Promise<WorkflowRunState[]> {
    const results: WorkflowRunState[] = [];

    for (const run of this.runs.values()) {
      if (
        run.status !== WorkflowRunStatus.ACTIVE &&
        run.status !== WorkflowRunStatus.PAUSED
      ) {
        continue;
      }
      if (options?.workflowId && run.workflowId !== options.workflowId) {
        continue;
      }
      if (options?.projectId && run.projectId !== options.projectId) {
        continue;
      }
      results.push(run);
    }

    // Sort by updatedAt descending (most recent first)
    results.sort((a, b) => {
      const aTime = a.updatedAt ?? "";
      const bTime = b.updatedAt ?? "";
      return bTime.localeCompare(aTime);
    });

    return results;
  }

  async commit(): Promise<void> {
    // No-op for in-memory store.
  }
}
