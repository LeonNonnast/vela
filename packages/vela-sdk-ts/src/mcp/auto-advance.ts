/**
 * Auto-advance loop logic for workflow execution.
 *
 * Elicit -> commit -> advance loop. Stops at steps that require
 * agent work: EXECUTE, DIALOG, WORKFLOW, or incomplete captures.
 */

import type {
  AdvanceResult,
  WorkflowRunState,
} from "../engine/types.js";
import type { IWorkflowEngine } from "../engine/workflow-engine.js";
import type { ResourceResolver } from "../engine/prompt-builder.js";
import type { Locale } from "../locale/locale.js";
import { getLocale } from "../locale/locale.js";
import type {
  AnyStepDefinition,
  WorkflowDefinition,
} from "../schemas/workflow.js";
import type { WorkflowStore } from "../storage/store.js";
import type { McpContext } from "./mcp-server.js";
import { ElicitationService } from "./elicitation.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isAutomationMode(run: WorkflowRunState): boolean {
  const val = run.params["automation_mode"];
  return val === true || val === "true" || val === 1;
}

// ---------------------------------------------------------------------------
// stepCapturesComplete
// ---------------------------------------------------------------------------

export function stepCapturesComplete(
  stepDef: AnyStepDefinition,
  run: WorkflowRunState,
): boolean {
  const elicitable = stepDef.capture.filter((cap) => cap.elicit !== "never");
  if (elicitable.length === 0) {
    return true;
  }
  return elicitable.every((cap) => cap.key in run.stateData);
}

// ---------------------------------------------------------------------------
// elicitStepCaptures
// ---------------------------------------------------------------------------

export async function elicitStepCaptures(
  ctx: McpContext,
  engine: IWorkflowEngine,
  wfDef: WorkflowDefinition,
  run: WorkflowRunState,
  store: WorkflowStore,
  locale?: Locale,
): Promise<WorkflowRunState> {
  const loc = locale ?? getLocale();

  const stepDef = engine.getStep(wfDef, run.currentStep ?? "");
  if (!stepDef || !stepDef.capture || stepDef.capture.length === 0) {
    return run;
  }

  // Dialog steps handle captures after all phases complete
  if (stepDef.type === "dialog") {
    return run;
  }

  let currentRun = run;

  for (const cap of stepDef.capture) {
    if (cap.elicit === "never") {
      continue;
    }
    // In automation mode: only elicit required captures, skip the rest
    if (isAutomationMode(currentRun) && !cap.required) {
      continue;
    }

    const existingValue = currentRun.stateData[cap.key];
    if (cap.elicit === "if_missing" && existingValue !== undefined && existingValue !== null) {
      continue;
    }

    const schema = ElicitationService.buildRequestedSchema(cap);
    let message = ElicitationService.buildMessage(cap);
    if (existingValue !== undefined && existingValue !== null) {
      message += loc.currentValueHint.replace(
        "{existing_value}",
        String(existingValue),
      );
    }

    let elicitResult;
    try {
      elicitResult = await ctx.elicit(message, schema);
    } catch {
      ctx.log.debug("elicitation.not_supported", { key: cap.key });
      return currentRun;
    }

    const processed = ElicitationService.processResult(cap, elicitResult);
    if (processed) {
      const [key, value] = processed;
      currentRun = await store.updateStep(currentRun.id, null, {
        stateData: { [key]: value },
      });
      await store.commit();
    }
  }

  return currentRun;
}

// ---------------------------------------------------------------------------
// autoAdvanceLoop
// ---------------------------------------------------------------------------

export async function autoAdvanceLoop(
  ctx: McpContext,
  engine: IWorkflowEngine,
  wfDef: WorkflowDefinition,
  result: AdvanceResult,
  store: WorkflowStore,
  resourceResolver?: ResourceResolver,
  locale?: Locale,
): Promise<AdvanceResult> {
  let current = result;

  while (!current.completed && current.run.currentStep && ctx) {
    const stepDef = engine.getStep(wfDef, current.run.currentStep ?? "");
    if (!stepDef) {
      break;
    }

    // Execute steps always need agent work
    if (stepDef.type === "execute") {
      break;
    }

    // Dialog steps need interactive multi-phase agent work
    if (stepDef.type === "dialog") {
      break;
    }

    // Workflow steps delegate to sub-workflows (handled by orchestrator)
    if (stepDef.type === "workflow") {
      break;
    }

    // Steps without elicitable captures need agent output
    const hasElicitable = stepDef.capture
      ? stepDef.capture.some((c) => c.elicit !== "never")
      : false;

    if (!hasElicitable) {
      const interactiveTypes = new Set(["confirm", "choice", "freeform"]);
      if (!interactiveTypes.has(stepDef.type)) {
        // If this is the final step, auto-advance to complete the workflow
        // We check by trying to advance — the engine resolves next step internally
        current = await engine.advance(current.run, wfDef, {
          resourceResolver,
        });
        await store.commit();
      }
      break;
    }

    current.run = await elicitStepCaptures(
      ctx,
      engine,
      wfDef,
      current.run,
      store,
      locale,
    );

    if (stepCapturesComplete(stepDef, current.run)) {
      current = await engine.advance(current.run, wfDef, {
        resourceResolver,
      });
      await store.commit();
    } else {
      await store.commit();
      break;
    }
  }

  return current;
}
