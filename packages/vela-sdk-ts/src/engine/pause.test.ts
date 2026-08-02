/**
 * pauseRun tests — explicit pause action gated on lifecycle.allow_pause.
 *
 * Resuming a paused run isn't a separate method: advance() already treats
 * PAUSED the same as ACTIVE, so calling it again is the resume path.
 */

import { describe, it, expect } from "vitest";
import { DefaultWorkflowEngine } from "./workflow-engine.js";
import { InMemoryStore } from "../storage/memory-store.js";
import { WorkflowRunStatus } from "./types.js";
import type { WorkflowDefinition } from "../schemas/workflow.js";

function buildWorkflow(allowPause: boolean | null = null): WorkflowDefinition {
  return {
    id: "wf-pause-test",
    version: "1.0.0",
    name: "Pause Test",
    description: "",
    params: [],
    context: null,
    lifecycle: allowPause === null ? null : { auto_archive_after: null, auto_cancel_after: null, allow_pause: allowPause },
    tools: [],
    resources: [],
    steps: [
      {
        type: "freeform",
        id: "s1",
        name: null,
        prompt: "Step 1",
        depends_on: [],
        fetch: [],
        tools: [],
        capture: [],
        next: "s2",
        notes: true,
        on_error: null,
        resources: [],
      },
      {
        type: "freeform",
        id: "s2",
        name: null,
        prompt: "Step 2",
        depends_on: [],
        fetch: [],
        tools: [],
        capture: [],
        next: null,
        notes: true,
        on_error: null,
        resources: [],
      },
    ],
  } as unknown as WorkflowDefinition;
}

describe("DefaultWorkflowEngine — pauseRun", () => {
  it("pauses an active run by default (allow_pause defaults to true)", async () => {
    const store = new InMemoryStore();
    const engine = new DefaultWorkflowEngine(store);
    const wf = buildWorkflow();
    const [run] = await engine.startOrResume(wf);

    const paused = await engine.pauseRun(run, wf);
    expect(paused.status).toBe(WorkflowRunStatus.PAUSED);
  });

  it("throws when lifecycle.allow_pause is false", async () => {
    const store = new InMemoryStore();
    const engine = new DefaultWorkflowEngine(store);
    const wf = buildWorkflow(false);
    const [run] = await engine.startOrResume(wf);

    await expect(engine.pauseRun(run, wf)).rejects.toThrow(/allow_pause/);
  });

  it("throws when the run isn't active", async () => {
    const store = new InMemoryStore();
    const engine = new DefaultWorkflowEngine(store);
    const wf = buildWorkflow();
    const [run] = await engine.startOrResume(wf);
    const paused = await engine.pauseRun(run, wf);

    await expect(engine.pauseRun(paused, wf)).rejects.toThrow(/not 'active'/);
  });

  it("resumes a paused run via advance() (no separate resume method needed)", async () => {
    // advance() already treats PAUSED the same as ACTIVE at the top of the
    // method (matches the pre-existing sub-workflow-pause precedent, where
    // status also isn't flipped back automatically) — it just keeps
    // processing the step transition.
    const store = new InMemoryStore();
    const engine = new DefaultWorkflowEngine(store);
    const wf = buildWorkflow();
    const [run] = await engine.startOrResume(wf);
    const paused = await engine.pauseRun(run, wf);

    const result = await engine.advance(paused, wf, { stepOutput: "ok" });
    expect(result.completed).toBe(false);
    expect(result.run.currentStep).toBe("s2");
  });
});
