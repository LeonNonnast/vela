/**
 * End-to-end mcp_call-step test against DefaultWorkflowEngine.
 *
 * Mirrors delegate-step.test.ts: builds a minimal workflow with a single
 * `mcp_call` step, registers a source handler, advances the run, and
 * asserts the handler was called, the capture landed in stateData, and
 * on_error (retry/fallback/abort) is applied automatically.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { DefaultWorkflowEngine } from "./workflow-engine.js";
import { InMemoryStore } from "../storage/memory-store.js";
import { registerSource, clearSources } from "../sources/registry.js";
import type { SourceHandler } from "../sources/types.js";
import type { WorkflowDefinition } from "../schemas/workflow.js";

/** Build a one-step workflow that runs the given mcp_call source/tool. */
function buildWorkflow(
  mcpSource: string,
  mcpTool = "do-thing",
  captureKey = "result",
  onError: unknown = null,
  extraSteps: unknown[] = [],
  mcpParams: Record<string, unknown> = { who: "{{params.who}}" },
): WorkflowDefinition {
  return {
    id: "wf-mcp-call-test",
    version: "1.0.0",
    name: "Mcp Call Test",
    description: "",
    params: [],
    context: null,
    lifecycle: null,
    tools: [],
    resources: [],
    steps: [
      {
        type: "mcp_call",
        id: "call-it",
        mcp_source: mcpSource,
        mcp_tool: mcpTool,
        mcp_params: mcpParams,
        name: null,
        prompt: "",
        depends_on: [],
        fetch: [],
        tools: [],
        capture: [
          {
            key: captureKey,
            label: null,
            type: "string",
            required: false,
            source: "output",
            input: null,
            options: [],
            suggest: false,
            placeholder: null,
            elicit: "never",
          },
        ],
        next: null,
        notes: true,
        on_error: onError,
        resources: [],
      },
      ...extraSteps,
    ],
  } as unknown as WorkflowDefinition;
}

/** Minimal freeform step usable as an on_error fallback target. */
function fallbackStep(id: string) {
  return {
    type: "freeform",
    id,
    name: null,
    prompt: `Recovering via ${id}`,
    depends_on: [],
    fetch: [],
    tools: [],
    capture: [],
    next: null,
    notes: true,
    on_error: null,
    resources: [],
  };
}

describe("DefaultWorkflowEngine — mcp_call step", () => {
  beforeEach(() => {
    clearSources();
  });

  it("invokes the registered source handler and captures its result", async () => {
    const calls: Array<{ tool: string; params: unknown }> = [];
    const handler: SourceHandler = async (tool, params) => {
      calls.push({ tool, params });
      return { result: "ok", echo: params };
    };
    registerSource("devops", handler);

    const store = new InMemoryStore();
    const engine = new DefaultWorkflowEngine(store);
    const wf = buildWorkflow("devops", "do-thing", "echo");

    const [run] = await engine.startOrResume(wf, { params: { who: "world" } });
    const result = await engine.advance(run, wf);

    expect(calls).toHaveLength(1);
    expect(calls[0].tool).toBe("do-thing");
    expect((calls[0].params as { who: string }).who).toBe("world");
    expect(result.completed).toBe(true);
    expect(result.run.stateData.echo).toEqual({ who: "world" });
  });

  it("throws when no handler is registered for mcp_source", async () => {
    const store = new InMemoryStore();
    const engine = new DefaultWorkflowEngine(store);
    const wf = buildWorkflow("nonexistent");

    const [run] = await engine.startOrResume(wf);
    // No on_error configured -> aborts (cancels) rather than throwing.
    const result = await engine.advance(run, wf);
    expect(result.run.status).toBe("cancelled");
    expect(result.error).toMatch(/No handler registered for source/);
  });

  it("propagates AbortSignal to the handler", async () => {
    let receivedSignal: AbortSignal | undefined;
    const handler: SourceHandler = async (_tool, _params, ctx) => {
      receivedSignal = ctx.signal;
      return null;
    };
    registerSource("signal-probe", handler);

    const store = new InMemoryStore();
    const engine = new DefaultWorkflowEngine(store);
    const wf = buildWorkflow("signal-probe");

    const ac = new AbortController();
    const [run] = await engine.startOrResume(wf);
    await engine.advance(run, wf, { signal: ac.signal });

    expect(receivedSignal).toBe(ac.signal);
  });

  it("retries a failing handler up to on_error.retry times, then succeeds", async () => {
    let attempts = 0;
    const handler: SourceHandler = async () => {
      attempts += 1;
      if (attempts < 3) {
        throw new Error("transient failure");
      }
      return { result: "ok" };
    };
    registerSource("flaky", handler);

    const store = new InMemoryStore();
    const engine = new DefaultWorkflowEngine(store);
    const wf = buildWorkflow("flaky", "do-thing", "result", {
      retry: 2,
      fallback: null,
      abort: false,
      message: null,
    });

    const [run] = await engine.startOrResume(wf);
    const out = await engine.advance(run, wf);

    expect(attempts).toBe(3);
    expect(out.error).toBeUndefined();
    expect(out.run.stateData.result).toBe("ok");
  });

  it("falls back to on_error.fallback when the handler keeps failing", async () => {
    const handler: SourceHandler = async () => {
      throw new Error("boom");
    };
    registerSource("always-fails", handler);

    const store = new InMemoryStore();
    const engine = new DefaultWorkflowEngine(store);
    const wf = buildWorkflow(
      "always-fails",
      "do-thing",
      "result",
      { retry: 0, fallback: "recover", abort: false, message: "source unavailable" },
      [fallbackStep("recover")],
    );

    const [run] = await engine.startOrResume(wf);
    const out = await engine.advance(run, wf);

    expect(out.completed).toBe(false);
    expect(out.error).toBe("source unavailable");
    expect(out.run.currentStep).toBe("recover");
    expect(out.run.stateData._error).toBe("source unavailable");
    expect(out.run.status).not.toBe("cancelled");
  });

  it("aborts (cancels the run) when the handler fails with no fallback configured", async () => {
    const handler: SourceHandler = async () => {
      throw new Error("fatal");
    };
    registerSource("fatal-handler", handler);

    const store = new InMemoryStore();
    const engine = new DefaultWorkflowEngine(store);
    const wf = buildWorkflow("fatal-handler", "do-thing", "result", {
      retry: 0,
      fallback: null,
      abort: true,
      message: null,
    });

    const [run] = await engine.startOrResume(wf);
    const out = await engine.advance(run, wf);

    expect(out.completed).toBe(true);
    expect(out.error).toBe("fatal");
    expect(out.run.status).toBe("cancelled");
    expect(out.run.stateData._error).toBe("fatal");
  });

  it("fails through on_error when mcp_source/mcp_tool are missing", async () => {
    const store = new InMemoryStore();
    const engine = new DefaultWorkflowEngine(store);
    const wf = buildWorkflow("", "", "result", {
      retry: 0,
      fallback: "recover",
      abort: false,
      message: null,
    }, [fallbackStep("recover")]);

    const [run] = await engine.startOrResume(wf);
    const out = await engine.advance(run, wf);

    expect(out.run.currentStep).toBe("recover");
    expect(out.error).toMatch(/missing mcp_source\/mcp_tool/);
  });
});
