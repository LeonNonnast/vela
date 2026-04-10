/**
 * Integration tests for the LangChain adapter.
 *
 * Verifies that the LangChainAdapter converts McpToolDefinitions
 * to LangChain DynamicStructuredTool instances and that the
 * createVelaToolkit convenience function works end-to-end.
 */

import { describe, it, expect } from "vitest";
import {
  LangChainAdapter,
  createVelaToolkit,
} from "../../src/adapters/langchain.js";
import {
  SIMPLE_WORKFLOW_YAML,
  CHOICE_WORKFLOW_YAML,
  MINIMAL_WORKFLOW_YAML,
} from "../fixtures/workflows.js";

// ---------------------------------------------------------------------------
// LangChainAdapter
// ---------------------------------------------------------------------------

describe("LangChainAdapter", () => {
  it("converts MCP tools to LangChain tools", () => {
    const { tools } = createVelaToolkit({
      workflows: [SIMPLE_WORKFLOW_YAML],
    });

    expect(tools).toHaveLength(3);
    const names = tools.map((t) => t.name);
    expect(names).toContain("workflow_advance");
    expect(names).toContain("workflow_status");
    expect(names).toContain("workflow_list");
  });

  it("tools have descriptions", () => {
    const { tools } = createVelaToolkit({
      workflows: [SIMPLE_WORKFLOW_YAML],
    });

    for (const tool of tools) {
      expect(tool.description).toBeTruthy();
    }
  });

  it("supports custom tool prefix", () => {
    const { tools } = createVelaToolkit({
      workflows: [SIMPLE_WORKFLOW_YAML],
      toolPrefix: "vela",
    });

    const names = tools.map((t) => t.name);
    expect(names).toContain("vela_advance");
    expect(names).toContain("vela_status");
    expect(names).toContain("vela_list");
  });

  it("collects prompts", () => {
    const { adapter } = createVelaToolkit({
      workflows: [SIMPLE_WORKFLOW_YAML, CHOICE_WORKFLOW_YAML],
    });

    const promptNames = adapter.listPrompts().map((p) => p.name);
    expect(promptNames).toContain("workflow_onboarding");
    expect(promptNames).toContain("workflow_support-ticket");
  });

  it("loads prompt content", async () => {
    const { adapter } = createVelaToolkit({
      workflows: [SIMPLE_WORKFLOW_YAML],
    });

    const content = await adapter.loadPrompt("workflow_onboarding");
    expect(content).toBeDefined();
    expect(content).toContain("onboarding");
  });
});

// ---------------------------------------------------------------------------
// Advance tool
// ---------------------------------------------------------------------------

describe("LangChain advance tool", () => {
  it("starts a workflow", async () => {
    const { tools } = createVelaToolkit({
      workflows: [SIMPLE_WORKFLOW_YAML],
      autoAdvance: false,
    });

    const advance = tools.find((t) => t.name === "workflow_advance")!;

    const resultJson = await advance.invoke({
      workflow_id: "onboarding",
      params: JSON.stringify({ user_name: "Alice" }),
    });

    const result = JSON.parse(resultJson);
    expect(result.run_id).toBeDefined();
    expect(result.workflow_id).toBe("onboarding");
    expect(result.current_step).toBe("welcome");
    expect(result.status).toBe("started");
  });

  it("advances a workflow with output", async () => {
    const { tools } = createVelaToolkit({
      workflows: [MINIMAL_WORKFLOW_YAML],
      autoAdvance: false,
    });

    const advance = tools.find((t) => t.name === "workflow_advance")!;

    // Start
    const startJson = await advance.invoke({
      workflow_id: "minimal",
    });
    const start = JSON.parse(startJson);
    expect(start.current_step).toBe("step1");

    // Advance with output — completes the single-step workflow
    const advanceJson = await advance.invoke({
      run_id: start.run_id,
      output: "Done!",
    });
    const advanced = JSON.parse(advanceJson);
    expect(advanced.status).toBe("completed");
  });
});

// ---------------------------------------------------------------------------
// Status tool
// ---------------------------------------------------------------------------

describe("LangChain status tool", () => {
  it("returns workflow run status", async () => {
    const { tools } = createVelaToolkit({
      workflows: [SIMPLE_WORKFLOW_YAML],
      autoAdvance: false,
    });

    const advance = tools.find((t) => t.name === "workflow_advance")!;
    const status = tools.find((t) => t.name === "workflow_status")!;

    // Start a workflow first
    const startJson = await advance.invoke({
      workflow_id: "onboarding",
      params: JSON.stringify({ user_name: "Charlie" }),
    });
    const start = JSON.parse(startJson);

    // Check status
    const statusJson = await status.invoke({
      run_id: start.run_id,
    });
    const statusResult = JSON.parse(statusJson);
    expect(statusResult.run_id).toBe(start.run_id);
    expect(statusResult.workflow_id).toBe("onboarding");
    expect(statusResult.current_step).toBe("welcome");
  });
});

// ---------------------------------------------------------------------------
// List tool
// ---------------------------------------------------------------------------

describe("LangChain list tool", () => {
  it("lists available workflows", async () => {
    const { tools } = createVelaToolkit({
      workflows: [SIMPLE_WORKFLOW_YAML, CHOICE_WORKFLOW_YAML],
    });

    const list = tools.find((t) => t.name === "workflow_list")!;
    const resultJson = await list.invoke({});
    const result = JSON.parse(resultJson);

    expect(result.definitions).toBeDefined();
    const ids = result.definitions.map((d: { id: string }) => d.id);
    expect(ids).toContain("onboarding");
    expect(ids).toContain("support-ticket");
  });
});

// ---------------------------------------------------------------------------
// End-to-end
// ---------------------------------------------------------------------------

describe("LangChain end-to-end workflow", () => {
  it("completes a minimal workflow", async () => {
    const { tools } = createVelaToolkit({
      workflows: [MINIMAL_WORKFLOW_YAML],
      autoAdvance: false,
    });

    const advance = tools.find((t) => t.name === "workflow_advance")!;

    // Start
    const startJson = await advance.invoke({
      workflow_id: "minimal",
    });
    const start = JSON.parse(startJson);
    expect(start.current_step).toBe("step1");

    // Complete the only step
    const completeJson = await advance.invoke({
      run_id: start.run_id,
      output: "Done!",
    });
    const complete = JSON.parse(completeJson);
    expect(complete.status).toBe("completed");
  });
});
