/**
 * End-to-end `fetch` step-field tests against DefaultWorkflowEngine.
 *
 * `fetch` is a BaseStepDefinition field (any step type can declare it), run
 * once when the engine lands on that step, exposed as {{fetch.x}}. Uses the
 * same source registry as mcp_call (../sources/registry.ts).
 */

import { describe, it, expect, beforeEach } from "vitest";
import { DefaultWorkflowEngine } from "./workflow-engine.js";
import { InMemoryStore } from "../storage/memory-store.js";
import { registerSource, clearSources } from "../sources/registry.js";
import type { SourceHandler } from "../sources/types.js";
import type { WorkflowDefinition } from "../schemas/workflow.js";

function freeformStep(
  id: string,
  prompt: string,
  fetch: unknown[] = [],
  onError: unknown = null,
  next: string | null = null,
) {
  return {
    type: "freeform",
    id,
    name: null,
    prompt,
    depends_on: [],
    fetch,
    tools: [],
    capture: [],
    next,
    notes: true,
    on_error: onError,
    resources: [],
  };
}

function buildWorkflow(steps: unknown[]): WorkflowDefinition {
  return {
    id: "wf-fetch-test",
    version: "1.0.0",
    name: "Fetch Test",
    description: "",
    params: [],
    context: null,
    lifecycle: null,
    tools: [],
    resources: [],
    steps,
  } as unknown as WorkflowDefinition;
}

describe("DefaultWorkflowEngine — fetch step field", () => {
  beforeEach(() => {
    clearSources();
  });

  it("populates {{fetch.x}} for the first step via startOrResume", async () => {
    const handler: SourceHandler = async (tool, params) => {
      expect(tool).toBe("get-status");
      expect(params).toEqual({});
      return "green";
    };
    registerSource("devops", handler);

    const wf = buildWorkflow([
      freeformStep("s1", "Status is {{fetch.status}}.", [
        { key: "status", source: "devops", action: "get-status", params: {} },
      ]),
    ]);

    const store = new InMemoryStore();
    const engine = new DefaultWorkflowEngine(store);
    const [run] = await engine.startOrResume(wf);

    expect(run.stateData._fetch).toEqual({ status: "green" });
    expect(engine.assemblePrompt(wf, run)).toContain("Status is green.");
  });

  it("populates {{fetch.x}} when landing on a later step via advance()", async () => {
    const handler: SourceHandler = async () => "42";
    registerSource("devops", handler);

    const wf = buildWorkflow([
      freeformStep("s1", "Step 1", [], null, "s2"),
      freeformStep("s2", "Count is {{fetch.count}}.", [
        { key: "count", source: "devops", action: "get-count", params: {} },
      ]),
    ]);

    const store = new InMemoryStore();
    const engine = new DefaultWorkflowEngine(store);
    const [run] = await engine.startOrResume(wf);
    const out = await engine.advance(run, wf, { stepOutput: "ok" });

    expect(out.run.currentStep).toBe("s2");
    expect(out.run.stateData._fetch).toEqual({ count: "42" });
    expect(out.prompt).toContain("Count is 42.");
  });

  it("resolves fetch params via templates against params/state", async () => {
    const calls: unknown[] = [];
    const handler: SourceHandler = async (_tool, params) => {
      calls.push(params);
      return "ok";
    };
    registerSource("devops", handler);

    const wf: WorkflowDefinition = {
      ...buildWorkflow([
        freeformStep("s1", "{{fetch.result}}", [
          { key: "result", source: "devops", action: "lookup", params: { who: "{{params.who}}" } },
        ]),
      ]),
      params: [{ name: "who", label: null, description: null, required: false, default: null, identity: false, application: false, resolve: false }],
    } as unknown as WorkflowDefinition;

    const store = new InMemoryStore();
    const engine = new DefaultWorkflowEngine(store);
    await engine.startOrResume(wf, { params: { who: "alice" } });

    expect(calls).toEqual([{ who: "alice" }]);
  });

  it("does not touch stateData when a step declares no fetch (no behavior change)", async () => {
    const wf = buildWorkflow([freeformStep("s1", "hello")]);
    const store = new InMemoryStore();
    const engine = new DefaultWorkflowEngine(store);
    const [run] = await engine.startOrResume(wf);

    expect(run.stateData._fetch).toBeUndefined();
  });

  it("falls back to on_error.fallback when the fetch handler keeps failing", async () => {
    registerSource("always-fails", async () => {
      throw new Error("boom");
    });

    const wf = buildWorkflow([
      freeformStep(
        "s1",
        "Data: {{fetch.x}}",
        [{ key: "x", source: "always-fails", action: "get", params: {} }],
        { retry: 0, fallback: "recover", abort: false, message: "fetch unavailable" },
      ),
      freeformStep("recover", "Recovering"),
    ]);

    const store = new InMemoryStore();
    const engine = new DefaultWorkflowEngine(store);
    const [run] = await engine.startOrResume(wf);

    expect(run.currentStep).toBe("recover");
    expect(run.stateData._error).toBe("fetch unavailable");
  });

  it("retries a failing fetch handler up to on_error.retry times, then succeeds", async () => {
    let attempts = 0;
    registerSource("flaky", async () => {
      attempts += 1;
      if (attempts < 2) {
        throw new Error("transient");
      }
      return "recovered";
    });

    const wf = buildWorkflow([
      freeformStep("s1", "{{fetch.x}}", [
        { key: "x", source: "flaky", action: "get", params: {} },
      ], { retry: 1, fallback: null, abort: false, message: null }),
    ]);

    const store = new InMemoryStore();
    const engine = new DefaultWorkflowEngine(store);
    const [run] = await engine.startOrResume(wf);

    expect(attempts).toBe(2);
    expect(run.stateData._fetch).toEqual({ x: "recovered" });
  });

  it("clears stale _fetch when landing on a step with no fetch declared", async () => {
    registerSource("devops", async () => "value");

    const wf = buildWorkflow([
      freeformStep("s1", "{{fetch.x}}", [
        { key: "x", source: "devops", action: "get", params: {} },
      ], null, "s2"),
      freeformStep("s2", "no fetch here"),
    ]);

    const store = new InMemoryStore();
    const engine = new DefaultWorkflowEngine(store);
    const [run] = await engine.startOrResume(wf);
    expect(run.stateData._fetch).toEqual({ x: "value" });

    const out = await engine.advance(run, wf, { stepOutput: "ok" });
    expect(out.run.currentStep).toBe("s2");
    expect(out.run.stateData._fetch).toEqual({});
  });
});
