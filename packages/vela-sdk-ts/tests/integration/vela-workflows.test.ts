/**
 * Integration tests for VelaWorkflows.
 *
 * Uses a mock McpServerAdapter to verify tool/prompt registration
 * and end-to-end workflow execution.
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  VelaWorkflows,
  type McpServerAdapter,
  type McpToolDefinition,
  type McpPromptDefinition,
  type McpContext,
  type ElicitResult,
  deLocale,
} from "../../src/index.js";
import {
  SIMPLE_WORKFLOW_YAML,
  CHOICE_WORKFLOW_YAML,
  AGENT_YAML,
  MINIMAL_WORKFLOW_YAML,
} from "../fixtures/workflows.js";

// ---------------------------------------------------------------------------
// Mock McpServerAdapter
// ---------------------------------------------------------------------------

class MockMcpServer implements McpServerAdapter {
  tools: McpToolDefinition[] = [];
  prompts: McpPromptDefinition[] = [];

  addTool(tool: McpToolDefinition): void {
    this.tools.push(tool);
  }

  addPrompt(prompt: McpPromptDefinition): void {
    this.prompts.push(prompt);
  }

  getTool(name: string): McpToolDefinition | undefined {
    return this.tools.find((t) => t.name === name);
  }

  getPrompt(name: string): McpPromptDefinition | undefined {
    return this.prompts.find((p) => p.name === name);
  }
}

// ---------------------------------------------------------------------------
// Mock McpContext
// ---------------------------------------------------------------------------

function createMockContext(
  elicitResponses: ElicitResult[] = [],
): McpContext {
  let elicitIndex = 0;
  return {
    async elicit(
      _message: string,
      _schema: Record<string, unknown>,
    ): Promise<ElicitResult> {
      if (elicitIndex < elicitResponses.length) {
        return elicitResponses[elicitIndex++];
      }
      return { action: "decline" };
    },
    log: {
      debug() {},
      info() {},
      warn() {},
      error() {},
    },
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("VelaWorkflows", () => {
  let server: MockMcpServer;

  beforeEach(() => {
    server = new MockMcpServer();
  });

  // -----------------------------------------------------------------------
  // Tool registration
  // -----------------------------------------------------------------------

  it("registers 3 tools with correct default names", () => {
    new VelaWorkflows({
      server,
      workflows: [SIMPLE_WORKFLOW_YAML],
    });

    expect(server.tools).toHaveLength(3);
    const names = server.tools.map((t) => t.name);
    expect(names).toContain("workflow_advance");
    expect(names).toContain("workflow_status");
    expect(names).toContain("workflow_list");
  });

  // -----------------------------------------------------------------------
  // Prompt registration
  // -----------------------------------------------------------------------

  it("registers workflow prompts for each workflow", () => {
    new VelaWorkflows({
      server,
      workflows: [SIMPLE_WORKFLOW_YAML, CHOICE_WORKFLOW_YAML],
    });

    const promptNames = server.prompts.map((p) => p.name);
    expect(promptNames).toContain("workflow_onboarding");
    expect(promptNames).toContain("workflow_support-ticket");
  });

  it("does not register prompts when registerPrompts is false", () => {
    new VelaWorkflows({
      server,
      workflows: [SIMPLE_WORKFLOW_YAML],
      registerPrompts: false,
    });

    expect(server.prompts).toHaveLength(0);
  });

  // -----------------------------------------------------------------------
  // Advance: start workflow
  // -----------------------------------------------------------------------

  it("advance starts a workflow by workflow_id", async () => {
    new VelaWorkflows({
      server,
      workflows: [SIMPLE_WORKFLOW_YAML],
      autoAdvance: false,
    });

    const ctx = createMockContext();
    const advanceTool = server.getTool("workflow_advance")!;

    const resultJson = await advanceTool.execute(
      {
        workflow_id: "onboarding",
        params: JSON.stringify({ user_name: "Alice" }),
      },
      ctx,
    );

    const result = JSON.parse(resultJson);
    expect(result.run_id).toBeDefined();
    expect(result.workflow_id).toBe("onboarding");
    expect(result.current_step).toBe("welcome");
    expect(result.status).toBe("started");
  });

  // -----------------------------------------------------------------------
  // Advance: advance step with output
  // -----------------------------------------------------------------------

  it("advance advances a step with output", async () => {
    new VelaWorkflows({
      server,
      workflows: [SIMPLE_WORKFLOW_YAML],
      autoAdvance: false,
    });

    const ctx = createMockContext();
    const advanceTool = server.getTool("workflow_advance")!;

    // Start workflow
    const startJson = await advanceTool.execute(
      {
        workflow_id: "onboarding",
        params: JSON.stringify({ user_name: "Bob" }),
      },
      ctx,
    );
    const start = JSON.parse(startJson);
    expect(start.current_step).toBe("welcome");

    // Advance with output
    const advanceJson = await advanceTool.execute(
      {
        run_id: start.run_id,
        output: "My goal is to learn TypeScript",
      },
      ctx,
    );
    const advance = JSON.parse(advanceJson);
    expect(advance.current_step).toBe("confirm_role");
    expect(advance.completed).toBe(false);
  });

  // -----------------------------------------------------------------------
  // List workflows
  // -----------------------------------------------------------------------

  it("list returns definitions and active runs", async () => {
    new VelaWorkflows({
      server,
      workflows: [SIMPLE_WORKFLOW_YAML, CHOICE_WORKFLOW_YAML],
      autoAdvance: false,
    });

    const ctx = createMockContext();
    const advanceTool = server.getTool("workflow_advance")!;
    const listTool = server.getTool("workflow_list")!;

    // Start a workflow to create an active run
    await advanceTool.execute(
      {
        workflow_id: "onboarding",
        params: JSON.stringify({ user_name: "Test" }),
      },
      ctx,
    );

    const listJson = await listTool.execute({}, ctx);
    const list = JSON.parse(listJson);

    expect(list.definitions).toHaveLength(2);
    expect(list.definitions.map((d: any) => d.id)).toContain(
      "onboarding",
    );
    expect(list.definitions.map((d: any) => d.id)).toContain(
      "support-ticket",
    );
    expect(list.active_runs.length).toBeGreaterThanOrEqual(1);
  });

  // -----------------------------------------------------------------------
  // Status
  // -----------------------------------------------------------------------

  it("status returns run details", async () => {
    new VelaWorkflows({
      server,
      workflows: [MINIMAL_WORKFLOW_YAML],
      autoAdvance: false,
    });

    const ctx = createMockContext();
    const advanceTool = server.getTool("workflow_advance")!;
    const statusTool = server.getTool("workflow_status")!;

    const startJson = await advanceTool.execute(
      { workflow_id: "minimal" },
      ctx,
    );
    const start = JSON.parse(startJson);

    const statusJson = await statusTool.execute(
      { run_id: start.run_id },
      ctx,
    );
    const status = JSON.parse(statusJson);
    expect(status.run_id).toBe(start.run_id);
    expect(status.workflow_id).toBe("minimal");
    expect(status.current_step).toBe("step1");
    expect(status.status).toBe("active");
  });

  // -----------------------------------------------------------------------
  // Custom tool names
  // -----------------------------------------------------------------------

  it("supports custom tool name format", () => {
    new VelaWorkflows({
      server,
      workflows: [SIMPLE_WORKFLOW_YAML],
      toolNameFormat: {
        advance: "wf_go",
        status: "wf_check",
        list: "wf_all",
      },
    });

    const names = server.tools.map((t) => t.name);
    expect(names).toContain("wf_go");
    expect(names).toContain("wf_check");
    expect(names).toContain("wf_all");
  });

  // -----------------------------------------------------------------------
  // German locale
  // -----------------------------------------------------------------------

  it("uses German locale strings in responses", async () => {
    new VelaWorkflows({
      server,
      workflows: [MINIMAL_WORKFLOW_YAML],
      locale: deLocale(),
      autoAdvance: false,
    });

    const ctx = createMockContext();
    const advanceTool = server.getTool("workflow_advance")!;

    // Start and complete the workflow
    const startJson = await advanceTool.execute(
      { workflow_id: "minimal" },
      ctx,
    );
    const start = JSON.parse(startJson);

    const advanceJson = await advanceTool.execute(
      { run_id: start.run_id, output: "done" },
      ctx,
    );
    const advance = JSON.parse(advanceJson);

    // Completed workflow should show German text
    expect(advance.next_action).toContain("abgeschlossen");
  });

  // -----------------------------------------------------------------------
  // Agent prompts
  // -----------------------------------------------------------------------

  it("registers agent prompts", () => {
    new VelaWorkflows({
      server,
      workflows: [SIMPLE_WORKFLOW_YAML],
      agents: [AGENT_YAML],
    });

    const promptNames = server.prompts.map((p) => p.name);
    expect(promptNames).toContain("agent_support-agent");
  });

  it("agent prompt contains persona and workflows", async () => {
    new VelaWorkflows({
      server,
      workflows: [SIMPLE_WORKFLOW_YAML],
      agents: [AGENT_YAML],
    });

    const ctx = createMockContext();
    const agentPrompt = server.getPrompt("agent_support-agent")!;
    const content = await agentPrompt.load(ctx);

    expect(content).toContain("Support Agent");
    expect(content).toContain("helpful support agent");
    expect(content).toContain("support-ticket");
    expect(content).toContain("onboarding");
  });

  // -----------------------------------------------------------------------
  // Custom tool prefix
  // -----------------------------------------------------------------------

  it("uses custom tool prefix", () => {
    new VelaWorkflows({
      server,
      workflows: [SIMPLE_WORKFLOW_YAML],
      toolPrefix: "vela",
    });

    const names = server.tools.map((t) => t.name);
    expect(names).toContain("vela_advance");
    expect(names).toContain("vela_status");
    expect(names).toContain("vela_list");

    const promptNames = server.prompts.map((p) => p.name);
    expect(promptNames).toContain("vela_onboarding");
  });

  // -----------------------------------------------------------------------
  // Error handling
  // -----------------------------------------------------------------------

  it("returns error for unknown run_id", async () => {
    new VelaWorkflows({
      server,
      workflows: [SIMPLE_WORKFLOW_YAML],
    });

    const ctx = createMockContext();
    const advanceTool = server.getTool("workflow_advance")!;
    const resultJson = await advanceTool.execute(
      { run_id: "nonexistent-id" },
      ctx,
    );
    const result = JSON.parse(resultJson);
    expect(result.error).toBe("Run not found");
  });

  it("returns error for unknown workflow_id", async () => {
    new VelaWorkflows({
      server,
      workflows: [SIMPLE_WORKFLOW_YAML],
    });

    const ctx = createMockContext();
    const advanceTool = server.getTool("workflow_advance")!;
    const resultJson = await advanceTool.execute(
      { workflow_id: "nonexistent" },
      ctx,
    );
    const result = JSON.parse(resultJson);
    expect(result.error).toBe("Workflow not found");
  });

  it("returns error when neither workflow_id nor run_id provided", async () => {
    new VelaWorkflows({
      server,
      workflows: [SIMPLE_WORKFLOW_YAML],
    });

    const ctx = createMockContext();
    const advanceTool = server.getTool("workflow_advance")!;
    const resultJson = await advanceTool.execute({}, ctx);
    const result = JSON.parse(resultJson);
    expect(result.error).toBe("Provide workflow_id or run_id");
  });

  // -----------------------------------------------------------------------
  // register() method
  // -----------------------------------------------------------------------

  it("register adds workflow at runtime", async () => {
    const vw = new VelaWorkflows({
      server,
      workflows: [SIMPLE_WORKFLOW_YAML],
      autoAdvance: false,
    });

    const { parseWorkflowYaml } = await import(
      "../../src/loader/yaml-loader.js"
    );
    const minimalWf = parseWorkflowYaml(MINIMAL_WORKFLOW_YAML);
    vw.register(minimalWf);

    const ctx = createMockContext();
    const listTool = server.getTool("workflow_list")!;
    const listJson = await listTool.execute({}, ctx);
    const list = JSON.parse(listJson);

    const ids = list.definitions.map((d: any) => d.id);
    expect(ids).toContain("onboarding");
    expect(ids).toContain("minimal");
  });

  // -----------------------------------------------------------------------
  // Full workflow completion
  // -----------------------------------------------------------------------

  it("completes a full workflow end-to-end", async () => {
    new VelaWorkflows({
      server,
      workflows: [MINIMAL_WORKFLOW_YAML],
      autoAdvance: false,
    });

    const ctx = createMockContext();
    const advanceTool = server.getTool("workflow_advance")!;

    // Start
    const startJson = await advanceTool.execute(
      { workflow_id: "minimal" },
      ctx,
    );
    const start = JSON.parse(startJson);
    expect(start.current_step).toBe("step1");

    // Advance with output -> completes (only 1 step)
    const doneJson = await advanceTool.execute(
      { run_id: start.run_id, output: "result value" },
      ctx,
    );
    const done = JSON.parse(doneJson);
    expect(done.completed).toBe(true);

    // Verify status shows completed
    const statusTool = server.getTool("workflow_status")!;
    const statusJson = await statusTool.execute(
      { run_id: start.run_id },
      ctx,
    );
    const status = JSON.parse(statusJson);
    expect(status.status).toBe("completed");
  });
});
