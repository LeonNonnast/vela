/**
 * End-to-end delegate-step test against DefaultWorkflowEngine.
 *
 * Builds a minimal workflow with a single `delegate` step, registers a
 * handler, advances the run, and asserts the handler was called, the
 * capture landed in stateData, and AbortSignal propagation works.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { DefaultWorkflowEngine } from "./workflow-engine.js";
import { InMemoryStore } from "../storage/memory-store.js";
import {
  registerDelegate,
  clearDelegates,
} from "../delegate/registry.js";
import type { DelegateHandler } from "../delegate/types.js";
import type { WorkflowDefinition } from "../schemas/workflow.js";

/** Build a one-step workflow that runs the given delegate. */
function buildWorkflow(delegate: string, captureKey = "result"): WorkflowDefinition {
  return {
    id: "wf-delegate-test",
    version: "1.0.0",
    name: "Delegate Test",
    description: "",
    params: [],
    context: null,
    lifecycle: null,
    tools: [],
    resources: [],
    steps: [
      {
        type: "delegate",
        id: "do-it",
        delegate,
        task: { hello: "{{params.who}}" },
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
        on_error: null,
        resources: [],
      },
    ],
  } as unknown as WorkflowDefinition;
}

describe("DefaultWorkflowEngine — delegate step", () => {
  beforeEach(() => {
    clearDelegates();
  });

  it("invokes the registered handler and captures its result", async () => {
    const calls: Array<{ step: unknown; task: unknown }> = [];
    const handler: DelegateHandler = async (step, ctx) => {
      const resolvedTask = ctx.resolveVars(step.task);
      calls.push({ step, task: resolvedTask });
      return { result: "ok", echo: resolvedTask };
    };
    registerDelegate("test-echo", handler);

    const store = new InMemoryStore();
    const engine = new DefaultWorkflowEngine(store);
    const wf = buildWorkflow("test-echo", "echo");

    const [run] = await engine.startOrResume(wf, { params: { who: "world" } });
    const result = await engine.advance(run, wf);

    expect(calls).toHaveLength(1);
    expect((calls[0].task as { hello: string }).hello).toBe("world");
    expect(result.completed).toBe(true);
    // Capture key "echo" should hold the matching field from the handler result.
    expect(result.run.stateData.echo).toEqual({ hello: "world" });
  });

  it("throws when no handler is registered", async () => {
    const store = new InMemoryStore();
    const engine = new DefaultWorkflowEngine(store);
    const wf = buildWorkflow("nonexistent");

    const [run] = await engine.startOrResume(wf);
    await expect(engine.advance(run, wf)).rejects.toThrow(/No handler/);
  });

  it("propagates AbortSignal to the handler", async () => {
    let receivedSignal: AbortSignal | undefined;
    const handler: DelegateHandler = async (_step, ctx) => {
      receivedSignal = ctx.signal;
      return null;
    };
    registerDelegate("signal-probe", handler);

    const store = new InMemoryStore();
    const engine = new DefaultWorkflowEngine(store);
    const wf = buildWorkflow("signal-probe");

    const ac = new AbortController();
    const [run] = await engine.startOrResume(wf);
    await engine.advance(run, wf, { signal: ac.signal });

    expect(receivedSignal).toBe(ac.signal);
  });

  it("forwards setCapture values into the handler result", async () => {
    const handler: DelegateHandler = async (_step, ctx) => {
      ctx.setCapture("result", "from-setCapture");
      return null;
    };
    registerDelegate("set-capture", handler);

    const store = new InMemoryStore();
    const engine = new DefaultWorkflowEngine(store);
    const wf = buildWorkflow("set-capture", "result");

    const [run] = await engine.startOrResume(wf);
    const out = await engine.advance(run, wf);
    expect(out.run.stateData.result).toBe("from-setCapture");
  });
});
