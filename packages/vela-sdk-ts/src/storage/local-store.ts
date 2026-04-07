/**
 * KV-backed workflow store for browser localStorage, node-localstorage,
 * or any async key-value storage.
 */

import { WorkflowRunStatus } from "../engine/types.js";
import type { WorkflowRunState } from "../engine/types.js";
import type {
  CreateRunOptions,
  ListActiveOptions,
  UpdateStepOptions,
  WorkflowStore,
} from "./store.js";

/**
 * Minimal key-value storage interface.
 *
 * Compatible with browser `localStorage`, `node-localstorage`,
 * or any async KV store (e.g. Cloudflare KV, Redis wrappers).
 */
export interface KVStorage {
  getItem(key: string): Promise<string | null> | string | null;
  setItem(key: string, value: string): Promise<void> | void;
  removeItem(key: string): Promise<void> | void;
}

export class LocalStorageStore implements WorkflowStore {
  private readonly storage: KVStorage;
  private readonly prefix: string;

  constructor(storage: KVStorage, prefix = "vela:") {
    this.storage = storage;
    this.prefix = prefix;
  }

  // ── Key helpers ──────────────────────────────────────────────

  private runKey(runId: string): string {
    return `${this.prefix}run:${runId}`;
  }

  private get indexKey(): string {
    return `${this.prefix}index`;
  }

  // ── Index helpers ────────────────────────────────────────────

  private async getIndex(): Promise<string[]> {
    const raw = await this.storage.getItem(this.indexKey);
    if (!raw) return [];
    try {
      return JSON.parse(raw) as string[];
    } catch {
      return [];
    }
  }

  private async setIndex(ids: string[]): Promise<void> {
    await this.storage.setItem(this.indexKey, JSON.stringify(ids));
  }

  private async addToIndex(runId: string): Promise<void> {
    const ids = await this.getIndex();
    if (!ids.includes(runId)) {
      ids.push(runId);
      await this.setIndex(ids);
    }
  }

  private async removeFromIndex(runId: string): Promise<void> {
    const ids = await this.getIndex();
    const filtered = ids.filter((id) => id !== runId);
    await this.setIndex(filtered);
  }

  // ── Run serialization ────────────────────────────────────────

  private async loadRun(runId: string): Promise<WorkflowRunState | null> {
    const raw = await this.storage.getItem(this.runKey(runId));
    if (!raw) return null;
    try {
      return JSON.parse(raw) as WorkflowRunState;
    } catch {
      return null;
    }
  }

  private async saveRun(run: WorkflowRunState): Promise<void> {
    await this.storage.setItem(this.runKey(run.id), JSON.stringify(run));
  }

  // ── WorkflowStore implementation ────────────────────────────

  async findByIdentity(
    workflowId: string,
    identityParams: Record<string, string>,
  ): Promise<WorkflowRunState | null> {
    const ids = await this.getIndex();

    for (const id of ids) {
      const run = await this.loadRun(id);
      if (!run) continue;
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

    await this.saveRun(run);
    await this.addToIndex(run.id);
    return run;
  }

  async updateStep(
    runId: string,
    stepId: string | null,
    options?: UpdateStepOptions,
  ): Promise<WorkflowRunState> {
    const run = await this.loadRun(runId);
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
    await this.saveRun(run);
    return run;
  }

  async getById(runId: string): Promise<WorkflowRunState | null> {
    return this.loadRun(runId);
  }

  async listActive(options?: ListActiveOptions): Promise<WorkflowRunState[]> {
    const ids = await this.getIndex();
    const results: WorkflowRunState[] = [];

    for (const id of ids) {
      const run = await this.loadRun(id);
      if (!run) continue;
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

    results.sort((a, b) => {
      const aTime = a.updatedAt ?? "";
      const bTime = b.updatedAt ?? "";
      return bTime.localeCompare(aTime);
    });

    return results;
  }

  async commit(): Promise<void> {
    // KV writes are immediate; nothing to flush.
  }
}
