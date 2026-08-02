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

describe("PromptBuilder — buildTemplateContext: resolved.x / project.x / fetch.x", () => {
  it("exposes resolve-flagged params under `resolved`, unrelated params only under `params`", () => {
    const wf: WorkflowDefinition = {
      ...buildWorkflow(),
      params: [
        { name: "tenant", label: null, description: null, required: false, default: null, identity: false, application: false, resolve: true },
        { name: "who", label: null, description: null, required: false, default: null, identity: false, application: false, resolve: false },
      ],
    } as unknown as WorkflowDefinition;
    const run = { ...buildRun(), params: { tenant: "acme", who: "alice" } };

    const context = PromptBuilder.buildTemplateContext(wf, run);
    expect(context.resolved).toEqual({ tenant: "acme" });
    expect(context.params).toEqual({ tenant: "acme", who: "alice" });
  });

  it("leaves `project` empty when the run has no projectId or no resolver is given", () => {
    const wf = buildWorkflow();
    const run = buildRun();
    expect(PromptBuilder.buildTemplateContext(wf, run).project).toEqual({});

    const withProjectId = { ...run, projectId: "proj-1" };
    expect(PromptBuilder.buildTemplateContext(wf, withProjectId).project).toEqual({});
  });

  it("populates `project` from the injected projectDataResolver", () => {
    const wf = buildWorkflow();
    const run = { ...buildRun(), projectId: "proj-1" };
    const resolver = (projectId: string) => (projectId === "proj-1" ? { name: "Acme" } : undefined);

    const context = PromptBuilder.buildTemplateContext(wf, run, resolver);
    expect(context.project).toEqual({ name: "Acme" });
  });

  it("resolves {{resolved.x}} and {{project.x}} in an assembled prompt", () => {
    const wf: WorkflowDefinition = {
      ...buildWorkflow(),
      params: [
        { name: "tenant", label: null, description: null, required: false, default: null, identity: false, application: false, resolve: true },
      ],
    } as unknown as WorkflowDefinition;
    wf.steps[0].prompt = "Tenant {{resolved.tenant}} in project {{project.name}}";
    const run = { ...buildRun(), params: { tenant: "acme" }, projectId: "proj-1" };
    const resolver = () => ({ name: "Acme Corp" });

    const builder = new PromptBuilder();
    const prompt = builder.assemblePrompt(wf, run, wf.steps[0], undefined, undefined, resolver);
    expect(prompt).toContain("Tenant acme in project Acme Corp");
  });
});
