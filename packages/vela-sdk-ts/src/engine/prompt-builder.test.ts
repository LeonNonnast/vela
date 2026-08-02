import { describe, it, expect } from "vitest";
import { PromptBuilder } from "./prompt-builder.js";
import { WorkflowRunStatus } from "./types.js";
import type { WorkflowRunState } from "./types.js";
import type { WorkflowDefinition } from "../schemas/workflow.js";
import { getLocale } from "../locale/locale.js";

function buildWorkflow(): WorkflowDefinition {
  return {
    id: "wf-prompt-test",
    version: "1.0.0",
    name: "Prompt Test",
    description: "",
    params: [],
    context: null,
    lifecycle: null,
    tools: [],
    resources: [],
    steps: [
      {
        type: "confirm",
        id: "confirm-it",
        name: null,
        prompt: "Please confirm",
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

function buildRun(): WorkflowRunState {
  return {
    id: "r",
    workflowId: "wf-prompt-test",
    workflowVersion: "1.0.0",
    currentStep: "confirm-it",
    status: WorkflowRunStatus.ACTIVE,
    params: {},
    stateData: {},
  };
}

describe("PromptBuilder — locale", () => {
  it("defaults to English when no locale is passed", () => {
    const builder = new PromptBuilder();
    const wf = buildWorkflow();
    const run = buildRun();
    const prompt = builder.assemblePrompt(wf, run, wf.steps[0]);
    expect(prompt).toContain("### Progress");
    expect(prompt).toContain("**Please confirm or reject.**");
  });

  it("uses German strings when the German locale is passed explicitly", () => {
    const builder = new PromptBuilder();
    const wf = buildWorkflow();
    const run = buildRun();
    const prompt = builder.assemblePrompt(wf, run, wf.steps[0], undefined, getLocale("de"));
    expect(prompt).toContain("### Fortschritt");
    expect(prompt).toContain("**Bitte bestaetigen oder ablehnen.**");
  });
});
