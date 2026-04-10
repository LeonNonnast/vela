/**
 * Integration tests for the Azure AI Agents adapter.
 *
 * Verifies that the AzureAgentsAdapter converts McpToolDefinitions
 * to Azure function tool definitions, dispatches tool calls correctly,
 * and produces a prompt advisor with workflow info.
 */

import { describe, it, expect } from "vitest";
import {
  AzureAgentsAdapter,
  createVelaAzureToolset,
} from "../../src/adapters/azure-agents.js";
import type { AzureFunctionToolDefinition } from "../../src/adapters/azure-agents.js";
import {
  SIMPLE_WORKFLOW_YAML,
  CHOICE_WORKFLOW_YAML,
  MINIMAL_WORKFLOW_YAML,
} from "../fixtures/workflows.js";

// ---------------------------------------------------------------------------
// Tool definitions
// ---------------------------------------------------------------------------

describe("AzureAgentsAdapter tool definitions", () => {
  it("generates Azure function tool definitions from MCP tools", () => {
    const { tools } = createVelaAzureToolset({
      workflows: [SIMPLE_WORKFLOW_YAML],
    });

    expect(tools).toHaveLength(3);
    const names = tools.map((t) => t.function.name);
    expect(names).toContain("workflow_advance");
    expect(names).toContain("workflow_status");
    expect(names).toContain("workflow_list");
  });

  it("all tool definitions have type 'function'", () => {
    const { tools } = createVelaAzureToolset({
      workflows: [SIMPLE_WORKFLOW_YAML],
    });

    for (const tool of tools) {
      expect(tool.type).toBe("function");
    }
  });

  it("tool definitions include descriptions", () => {
    const { tools } = createVelaAzureToolset({
      workflows: [SIMPLE_WORKFLOW_YAML],
    });

    for (const tool of tools) {
      expect(tool.function.description).toBeTruthy();
    }
  });

  it("tool definitions have correct parameter schema structure", () => {
    const { tools } = createVelaAzureToolset({
      workflows: [SIMPLE_WORKFLOW_YAML],
    });

    for (const tool of tools) {
      expect(tool.function.parameters.type).toBe("object");
      expect(tool.function.parameters.properties).toBeDefined();
    }
  });

  it("advance tool has expected parameters", () => {
    const { tools } = createVelaAzureToolset({
      workflows: [SIMPLE_WORKFLOW_YAML],
    });

    const advance = tools.find((t) => t.function.name === "workflow_advance")!;
    expect(advance).toBeDefined();

    const props = advance.function.parameters.properties;
    expect(props["workflow_id"]).toBeDefined();
    expect(props["run_id"]).toBeDefined();
    expect(props["output"]).toBeDefined();
    expect(props["workflow_id"].type).toBe("string");
  });

  it("status tool has required parameters", () => {
    const { tools } = createVelaAzureToolset({
      workflows: [SIMPLE_WORKFLOW_YAML],
    });

    const status = tools.find((t) => t.function.name === "workflow_status")!;
    expect(status).toBeDefined();
    expect(status.function.parameters.required).toContain("run_id");
  });

  it("supports custom tool prefix", () => {
    const { tools } = createVelaAzureToolset({
      workflows: [SIMPLE_WORKFLOW_YAML],
      toolPrefix: "vela",
    });

    const names = tools.map((t) => t.function.name);
    expect(names).toContain("vela_advance");
    expect(names).toContain("vela_status");
    expect(names).toContain("vela_list");
  });
});

// ---------------------------------------------------------------------------
// Tool call dispatch
// ---------------------------------------------------------------------------

describe("AzureAgentsAdapter handleToolCall", () => {
  it("starts a workflow via handleToolCall", async () => {
    const { handleToolCall } = createVelaAzureToolset({
      workflows: [SIMPLE_WORKFLOW_YAML],
      autoAdvance: false,
    });

    const resultJson = await handleToolCall("workflow_advance", {
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
    const { handleToolCall } = createVelaAzureToolset({
      workflows: [MINIMAL_WORKFLOW_YAML],
      autoAdvance: false,
    });

    // Start
    const startJson = await handleToolCall("workflow_advance", {
      workflow_id: "minimal",
    });
    const start = JSON.parse(startJson);
    expect(start.current_step).toBe("step1");

    // Advance with output — completes the single-step workflow
    const advanceJson = await handleToolCall("workflow_advance", {
      run_id: start.run_id,
      output: "Done!",
    });
    const advanced = JSON.parse(advanceJson);
    expect(advanced.status).toBe("completed");
  });

  it("returns error for unknown tool", async () => {
    const { handleToolCall } = createVelaAzureToolset({
      workflows: [SIMPLE_WORKFLOW_YAML],
    });

    const resultJson = await handleToolCall("nonexistent_tool", {});
    const result = JSON.parse(resultJson);
    expect(result.error).toBe("Unknown tool");
    expect(result.tool_name).toBe("nonexistent_tool");
  });

  it("returns workflow status via handleToolCall", async () => {
    const { handleToolCall } = createVelaAzureToolset({
      workflows: [SIMPLE_WORKFLOW_YAML],
      autoAdvance: false,
    });

    // Start a workflow first
    const startJson = await handleToolCall("workflow_advance", {
      workflow_id: "onboarding",
      params: JSON.stringify({ user_name: "Bob" }),
    });
    const start = JSON.parse(startJson);

    // Check status
    const statusJson = await handleToolCall("workflow_status", {
      run_id: start.run_id,
    });
    const statusResult = JSON.parse(statusJson);
    expect(statusResult.run_id).toBe(start.run_id);
    expect(statusResult.workflow_id).toBe("onboarding");
    expect(statusResult.current_step).toBe("welcome");
  });

  it("lists workflows via handleToolCall", async () => {
    const { handleToolCall } = createVelaAzureToolset({
      workflows: [SIMPLE_WORKFLOW_YAML, CHOICE_WORKFLOW_YAML],
    });

    const resultJson = await handleToolCall("workflow_list", {});
    const result = JSON.parse(resultJson);

    expect(result.definitions).toBeDefined();
    const ids = result.definitions.map((d: { id: string }) => d.id);
    expect(ids).toContain("onboarding");
    expect(ids).toContain("support-ticket");
  });
});

// ---------------------------------------------------------------------------
// Prompt advisor
// ---------------------------------------------------------------------------

describe("AzureAgentsAdapter promptAdvisor", () => {
  it("contains workflow tool information", () => {
    const { promptAdvisor } = createVelaAzureToolset({
      workflows: [SIMPLE_WORKFLOW_YAML],
    });

    expect(promptAdvisor).toContain("Vela Workflow Tools");
    expect(promptAdvisor).toContain("workflow_advance");
    expect(promptAdvisor).toContain("workflow_status");
    expect(promptAdvisor).toContain("workflow_list");
  });

  it("contains workflow prompt descriptions", () => {
    const { promptAdvisor } = createVelaAzureToolset({
      workflows: [SIMPLE_WORKFLOW_YAML, CHOICE_WORKFLOW_YAML],
    });

    expect(promptAdvisor).toContain("Available Workflows");
    expect(promptAdvisor).toContain("workflow_onboarding");
    expect(promptAdvisor).toContain("workflow_support-ticket");
  });

  it("includes next_action guidance", () => {
    const { promptAdvisor } = createVelaAzureToolset({
      workflows: [SIMPLE_WORKFLOW_YAML],
    });

    expect(promptAdvisor).toContain("next_action");
  });
});

// ---------------------------------------------------------------------------
// Adapter prompts
// ---------------------------------------------------------------------------

describe("AzureAgentsAdapter prompts", () => {
  it("collects prompts from workflows", () => {
    const { adapter } = createVelaAzureToolset({
      workflows: [SIMPLE_WORKFLOW_YAML, CHOICE_WORKFLOW_YAML],
    });

    const promptNames = adapter.listPrompts().map((p) => p.name);
    expect(promptNames).toContain("workflow_onboarding");
    expect(promptNames).toContain("workflow_support-ticket");
  });

  it("loads prompt content", async () => {
    const { adapter } = createVelaAzureToolset({
      workflows: [SIMPLE_WORKFLOW_YAML],
    });

    const content = await adapter.loadPrompt("workflow_onboarding");
    expect(content).toBeDefined();
    expect(content).toContain("onboarding");
  });
});

// ---------------------------------------------------------------------------
// End-to-end
// ---------------------------------------------------------------------------

describe("Azure AI Agents end-to-end workflow", () => {
  it("completes a minimal workflow through handleToolCall", async () => {
    const { handleToolCall } = createVelaAzureToolset({
      workflows: [MINIMAL_WORKFLOW_YAML],
      autoAdvance: false,
    });

    // Start
    const startJson = await handleToolCall("workflow_advance", {
      workflow_id: "minimal",
    });
    const start = JSON.parse(startJson);
    expect(start.current_step).toBe("step1");

    // Complete the only step
    const completeJson = await handleToolCall("workflow_advance", {
      run_id: start.run_id,
      output: "Done!",
    });
    const complete = JSON.parse(completeJson);
    expect(complete.status).toBe("completed");
  });
});
