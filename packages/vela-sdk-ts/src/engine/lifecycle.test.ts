import { describe, it, expect } from "vitest";
import { LifecycleChecker } from "./lifecycle.js";
import { WorkflowRunStatus } from "./types.js";
import type { WorkflowRunState } from "./types.js";
import type { LifecycleDefinition } from "../schemas/workflow.js";

function makeRun(overrides: Partial<WorkflowRunState>): WorkflowRunState {
  return {
    id: "r",
    workflowId: "w",
    workflowVersion: "1",
    status: WorkflowRunStatus.ACTIVE,
    params: {},
    stateData: {},
    updatedAt: new Date().toISOString(),
    ...overrides,
  };
}

function makeLifecycle(overrides: Partial<LifecycleDefinition>): LifecycleDefinition {
  return { auto_archive_after: null, auto_cancel_after: null, allow_pause: true, ...overrides };
}

function hoursAgo(hours: number): string {
  return new Date(Date.now() - hours * 60 * 60 * 1000).toISOString();
}

describe("LifecycleChecker", () => {
  it("cancels an active run past auto_cancel_after", () => {
    const run = makeRun({ status: WorkflowRunStatus.ACTIVE, updatedAt: hoursAgo(2) });
    const result = LifecycleChecker.checkLifecycle(run, makeLifecycle({ auto_cancel_after: "1h" }));
    expect(result).toBe(WorkflowRunStatus.CANCELLED);
  });

  it("does not cancel a recently updated active run", () => {
    const run = makeRun({ status: WorkflowRunStatus.ACTIVE, updatedAt: hoursAgo(0) });
    const result = LifecycleChecker.checkLifecycle(run, makeLifecycle({ auto_cancel_after: "1h" }));
    expect(result).toBeNull();
  });

  it("archives a completed run past auto_archive_after", () => {
    const run = makeRun({ status: WorkflowRunStatus.COMPLETED, updatedAt: hoursAgo(31 * 24) });
    const result = LifecycleChecker.checkLifecycle(run, makeLifecycle({ auto_archive_after: "30d" }));
    expect(result).toBe(WorkflowRunStatus.ARCHIVED);
  });

  it("does not archive a recently completed run", () => {
    const run = makeRun({ status: WorkflowRunStatus.COMPLETED, updatedAt: hoursAgo(0) });
    const result = LifecycleChecker.checkLifecycle(run, makeLifecycle({ auto_archive_after: "30d" }));
    expect(result).toBeNull();
  });

  it("does not archive a run that is not completed", () => {
    const run = makeRun({ status: WorkflowRunStatus.ACTIVE, updatedAt: hoursAgo(31 * 24) });
    const result = LifecycleChecker.checkLifecycle(run, makeLifecycle({ auto_archive_after: "30d" }));
    expect(result).toBeNull();
  });
});
