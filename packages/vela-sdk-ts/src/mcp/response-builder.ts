/**
 * Response building helpers for workflow tool outputs.
 *
 * Constructs structured response dicts that MCP tools return to the LLM,
 * including next-action instructions based on step type.
 */

import type { AdvanceResult, WorkflowRunState } from "../engine/types.js";
import type { IWorkflowEngine } from "../engine/workflow-engine.js";
import type { ResourceResolver } from "../engine/prompt-builder.js";
import type { Locale } from "../locale/locale.js";
import { getLocale } from "../locale/locale.js";
import type { AnyStepDefinition, WorkflowDefinition } from "../schemas/workflow.js";
import type { WorkflowStore } from "../storage/store.js";
import type { WorkflowResolver } from "./protocols.js";

// ---------------------------------------------------------------------------
// toJson
// ---------------------------------------------------------------------------

export function toJson(obj: unknown): string {
  if (typeof obj === "object" && obj !== null) {
    return JSON.stringify(obj);
  }
  return String(obj);
}

// ---------------------------------------------------------------------------
// runToDict
// ---------------------------------------------------------------------------

export function runToDict(run: WorkflowRunState): Record<string, unknown> {
  return {
    run_id: run.id,
    workflow_id: run.workflowId,
    workflow_version: run.workflowVersion,
    current_step: run.currentStep,
    status: run.status ?? null,
    project_id: run.projectId ?? null,
    params: run.params,
    state_data: run.stateData,
    parent_run_id: run.parentRunId ?? null,
    started_at: run.startedAt ?? null,
    updated_at: run.updatedAt ?? null,
  };
}

// ---------------------------------------------------------------------------
// buildNextAction
// ---------------------------------------------------------------------------

export function buildNextAction(
  run: WorkflowRunState,
  wfDef: WorkflowDefinition,
  engine: IWorkflowEngine,
  toolName: string,
  locale?: Locale,
): string {
  const loc = locale ?? getLocale();

  if (run.status === "completed") {
    return loc.workflowCompleted;
  }

  const stepDef = engine.getStep(wfDef, run.currentStep ?? "");
  if (!stepDef) {
    return loc.workflowCompleted;
  }

  const state = run.stateData;

  const captured: Record<string, unknown> = {};
  const missingKeys: string[] = [];
  if (stepDef.capture) {
    for (const cap of stepDef.capture) {
      if (cap.key in state) {
        captured[cap.key] = state[cap.key];
      } else {
        missingKeys.push(cap.key);
      }
    }
  }

  let partialHint = "";
  if (Object.keys(captured).length > 0 && missingKeys.length > 0) {
    const capturedJson = JSON.stringify(captured);
    partialHint = loc.alreadyCaptured
      .replace("{captured_json}", capturedJson)
      .replace("{missing_keys}", missingKeys.join(", "));
  }

  const hasElicitable = stepDef.capture
    ? stepDef.capture.some((c) => c.elicit !== "never")
    : false;
  const automation =
    run.params["automation_mode"] === true ||
    run.params["automation_mode"] === "true" ||
    run.params["automation_mode"] === 1;

  const fmt = (template: string): string =>
    template
      .replace(/\{tool_name\}/g, toolName)
      .replace(/\{run_id\}/g, run.id)
      .replace(/\{partial_hint\}/g, partialHint);

  if (stepDef.type === "execute") {
    // Check if this step delegates to a subagent
    if ("delegate" in stepDef && stepDef.delegate) {
      return fmt(loc.executeDelegateSubagent);
    }
    const prefixTag = automation ? loc.executePrefixTag : "";
    return fmt(loc.executeTaskThenCall).replace("{prefix_tag}", prefixTag);
  }

  if (stepDef.type === "dialog") {
    const dialogPhase = state["_dialog_phase"];
    if (automation) {
      return fmt(dialogPhase ? loc.dialogAutoProcess : loc.dialogAutoStart);
    }
    return fmt(dialogPhase ? loc.dialogConverse : loc.dialogStart);
  }

  if (hasElicitable) {
    return fmt(automation ? loc.elicitAuto : loc.elicitManual);
  }

  if (stepDef.type === "choice" && "options" in stepDef && stepDef.options.length > 0) {
    const optionsStr = stepDef.options
      .map((o) => `"${o.key}"`)
      .join(", ");
    const template = automation ? loc.choiceAuto : loc.choiceManual;
    return fmt(template).replace("{options_str}", optionsStr);
  }

  if (stepDef.type === "confirm") {
    return fmt(automation ? loc.confirmAuto : loc.confirmManual);
  }

  if (stepDef.type === "workflow") {
    const wfRef =
      ("workflow_ref" in stepDef ? stepDef.workflow_ref : null) ??
      "sub-workflow";
    return fmt(loc.subWorkflowStart).replace("{wf_ref}", wfRef);
  }

  return fmt(automation ? loc.fallbackAuto : loc.fallbackManual);
}

// ---------------------------------------------------------------------------
// buildResponse
// ---------------------------------------------------------------------------

export function buildResponse(
  result: AdvanceResult,
  wfDef: WorkflowDefinition,
  engine: IWorkflowEngine,
  toolName: string,
  locale?: Locale,
): Record<string, unknown> {
  const d: Record<string, unknown> = {
    run_id: result.run.id,
    current_step: result.run.currentStep,
    status: result.run.status ?? null,
    completed: result.completed,
  };

  if (result.prompt) {
    d["prompt"] = result.prompt;
  }

  if (result.subWorkflowRef) {
    d["sub_workflow"] = {
      ref: result.subWorkflowRef,
      params: result.subWorkflowParams,
    };
  }

  if (result.delegate) {
    d["delegate"] = result.delegate;
    if (result.delegateInstructions) {
      d["delegate_instructions"] = result.delegateInstructions;
    }
    if (result.delegateTools) {
      d["delegate_tools"] = result.delegateTools;
    }
  }

  d["next_action"] = buildNextAction(
    result.run,
    wfDef,
    engine,
    toolName,
    locale,
  );

  return d;
}

// ---------------------------------------------------------------------------
// buildStepResponse
// ---------------------------------------------------------------------------

export function buildStepResponse(
  run: WorkflowRunState,
  wfDef: WorkflowDefinition,
  engine: IWorkflowEngine,
  resolver: ResourceResolver | undefined,
  toolName: string,
  status: string = "active",
  locale?: Locale,
): Record<string, unknown> {
  const prompt = engine.assemblePrompt(wfDef, run, undefined, resolver);
  return {
    status,
    run_id: run.id,
    workflow_id: wfDef.id,
    current_step: run.currentStep,
    prompt,
    next_action: buildNextAction(run, wfDef, engine, toolName, locale),
  };
}

// ---------------------------------------------------------------------------
// enrichSubWorkflowResponse
// ---------------------------------------------------------------------------

export async function enrichSubWorkflowResponse(
  response: Record<string, unknown>,
  result: AdvanceResult,
  resolver: WorkflowResolver | undefined | null,
  store: WorkflowStore | undefined | null,
  locale: Locale | undefined,
  toolName: string,
): Promise<void> {
  if (!result.subWorkflowRef || !resolver) {
    return;
  }

  const childWfDef = await resolver.getWorkflow(result.subWorkflowRef);
  if (!childWfDef) {
    return;
  }

  const loc = locale ?? getLocale();

  let subWfInfo = (response["sub_workflow"] as Record<string, unknown>) ?? {
    ref: result.subWorkflowRef,
    params: result.subWorkflowParams,
  };

  const parentData: Record<string, unknown> = {
    ...result.run.params,
    ...result.run.stateData,
  };
  const paramsSchema: Record<string, unknown>[] = [];
  let hasIdentity = false;

  for (const p of childWfDef.params) {
    const pInfo: Record<string, unknown> = {
      name: p.name,
      required: p.required,
    };
    if (p.label) pInfo["label"] = p.label;
    if (p.description) pInfo["description"] = p.description;
    if (p.default !== undefined && p.default !== null) {
      pInfo["default"] = p.default;
    }
    const mapping = (result.subWorkflowParams ?? {}) as Record<string, string>;
    const parentKey = mapping[p.name] ?? p.name;
    if (parentKey in parentData) {
      pInfo["resolved_value"] = parentData[parentKey];
    }
    pInfo["identity"] = p.identity;
    if (p.identity) hasIdentity = true;
    paramsSchema.push(pInfo);
  }

  subWfInfo["params"] = paramsSchema;

  // Include active runs when child has identity params
  if (hasIdentity && store) {
    try {
      const activeRuns = await store.listActive({
        workflowId: childWfDef.id,
      });
      if (activeRuns.length > 0) {
        subWfInfo["active_runs"] = activeRuns.map((r) => ({
          run_id: r.id,
          status: r.status ?? null,
          current_step: r.currentStep,
          params: r.params,
        }));
      }
    } catch {
      // Ignore lookup failures
    }
  }

  response["sub_workflow"] = subWfInfo;

  // Build enriched next_action with param info for WORKFLOW steps
  if (paramsSchema.length > 0) {
    const wfRef = result.subWorkflowRef;
    const paramLines: string[] = [];
    for (const p of paramsSchema) {
      const parts: string[] = [`  - \`${p["name"]}\``];
      if (p["label"]) parts.push(`(${p["label"]})`);
      if (p["required"]) parts.push("[required]");
      if (p["identity"]) parts.push("[identity]");
      if ("resolved_value" in p) {
        parts.push(`= "${p["resolved_value"]}"`);
      } else if (p["default"] !== undefined && p["default"] !== null) {
        parts.push(`default: "${p["default"]}"`);
      }
      if (p["description"]) parts.push(`\u2014 ${p["description"]}`);
      paramLines.push(parts.join(" "));
    }

    let activeHint = "";
    const subWfRuns = subWfInfo["active_runs"] as unknown[] | undefined;
    if (subWfRuns && subWfRuns.length > 0) {
      activeHint = loc.subWorkflowActiveRunsHint.replace(
        "{count}",
        String(subWfRuns.length),
      );
    }

    response["next_action"] = loc.subWorkflowEnrichedNextAction
      .replace("{wf_ref}", wfRef)
      .replace("{param_lines}", paramLines.join("\n"))
      .replace("{active_hint}", activeHint)
      .replace("{run_id}", result.run.id)
      .replace("{tool_name}", toolName);
  }
}

// ---------------------------------------------------------------------------
// buildRunOptions
// ---------------------------------------------------------------------------

export function buildRunOptions(
  wfDef: WorkflowDefinition,
  activeRuns: WorkflowRunState[],
  locale?: Locale,
): Record<string, Record<string, string>> {
  const loc = locale ?? getLocale();

  const stepNames: Record<string, string> = {};
  for (const s of wfDef.steps) {
    stepNames[s.id] = s.name ?? s.id;
  }

  const paramLabels: Record<string, string> = {};
  for (const p of wfDef.params) {
    paramLabels[p.name] = p.label ?? p.name;
  }

  const options: Record<string, Record<string, string>> = {};
  for (const run of activeRuns) {
    const runParams = run.params;
    const paramParts: string[] = [];
    for (const pDef of wfDef.params) {
      if (pDef.name in runParams) {
        paramParts.push(
          `${paramLabels[pDef.name]}: ${runParams[pDef.name]}`,
        );
      }
    }
    const labelDetail =
      paramParts.length > 0 ? paramParts.join(", ") : run.id.slice(0, 8);
    const stepLabel = run.currentStep
      ? stepNames[run.currentStep] ?? run.currentStep
      : "";
    const stepInfo = stepLabel ? ` \u2014 ${stepLabel}` : "";
    options[run.id] = { title: `${labelDetail}${stepInfo}` };
  }

  options["__new__"] = { title: loc.newSession };
  return options;
}

// ---------------------------------------------------------------------------
// enrichToolRequirements
// ---------------------------------------------------------------------------

export function enrichToolRequirements(
  resp: Record<string, unknown>,
  wfDef: WorkflowDefinition,
  stepDef?: AnyStepDefinition | null,
): void {
  if (wfDef.tools.length > 0) {
    resp["required_tools"] = wfDef.tools.map((t) => ({
      name: t.name,
      server: t.server ?? null,
      description: t.description ?? null,
      required: t.required,
    }));
  }
  if (stepDef && stepDef.tools.length > 0) {
    resp["step_tools"] = stepDef.tools;
  }
}
