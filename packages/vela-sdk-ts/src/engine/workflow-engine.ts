/**
 * Core workflow state machine engine.
 *
 * Works against the WorkflowStore protocol -- no ORM dependency.
 * All state is accessed via WorkflowRunState (dicts, not JSON strings).
 *
 * Composes DialogHandler, PromptBuilder, and LifecycleChecker for
 * single-responsibility separation.
 */

import { DialogHandler } from "./dialog-handler.js";
import { LifecycleChecker } from "./lifecycle.js";
import { PromptBuilder, type ResourceResolver } from "./prompt-builder.js";
import {
  type AdvanceResult,
  type ErrorAction,
  type WorkflowRunState,
  WorkflowRunStatus,
} from "./types.js";
import type {
  AnyStepDefinition,
  CaptureDefinition,
  LifecycleDefinition,
  WorkflowDefinition,
} from "../schemas/workflow.js";
import type { WorkflowStore } from "../storage/store.js";

// ---------------------------------------------------------------------------
// Options types
// ---------------------------------------------------------------------------

export interface StartOptions {
  params?: Record<string, unknown>;
  projectId?: string | null;
  parentRunId?: string | null;
  parentStepId?: string | null;
}

export interface AdvanceOptions {
  stepOutput?: string | null;
  notes?: string | null;
  resourceResolver?: ResourceResolver;
}

// ---------------------------------------------------------------------------
// IWorkflowEngine
// ---------------------------------------------------------------------------

export interface IWorkflowEngine {
  startOrResume(
    workflowDef: WorkflowDefinition,
    options?: StartOptions,
  ): Promise<[WorkflowRunState, boolean]>;

  advance(
    run: WorkflowRunState,
    workflowDef: WorkflowDefinition,
    options?: AdvanceOptions,
  ): Promise<AdvanceResult>;

  assemblePrompt(
    workflowDef: WorkflowDefinition,
    run: WorkflowRunState,
    step?: AnyStepDefinition,
    resourceResolver?: ResourceResolver,
  ): string;

  getStep(
    workflowDef: WorkflowDefinition,
    stepId: string,
  ): AnyStepDefinition | undefined;

  checkLifecycle(
    run: WorkflowRunState,
    lifecycle?: LifecycleDefinition | null,
  ): WorkflowRunStatus | null;

  validateDependsOn(
    run: WorkflowRunState,
    step: AnyStepDefinition,
  ): [boolean, string[]];

  handleOnError(
    run: WorkflowRunState,
    step: AnyStepDefinition,
    error: string,
  ): ErrorAction;
}

// ---------------------------------------------------------------------------
// DefaultWorkflowEngine
// ---------------------------------------------------------------------------

export class DefaultWorkflowEngine implements IWorkflowEngine {
  private readonly store: WorkflowStore;
  private readonly promptBuilder: PromptBuilder;
  private readonly dialogHandler: DialogHandler;

  constructor(store: WorkflowStore) {
    this.store = store;
    this.promptBuilder = new PromptBuilder();
    this.dialogHandler = new DialogHandler(store, this.promptBuilder);
  }

  // -----------------------------------------------------------------------
  // startOrResume
  // -----------------------------------------------------------------------

  async startOrResume(
    workflowDef: WorkflowDefinition,
    options?: StartOptions,
  ): Promise<[WorkflowRunState, boolean]> {
    const params = options?.params;

    // Build identity params
    const identityParams: Record<string, string> = {};
    if (params) {
      for (const pDef of workflowDef.params) {
        if (pDef.identity && pDef.name in params) {
          identityParams[pDef.name] = String(params[pDef.name]);
        }
      }
    }

    // Try to find existing run by identity
    if (Object.keys(identityParams).length > 0) {
      const existing = await this.store.findByIdentity(
        workflowDef.id,
        identityParams,
      );
      if (existing) {
        return [existing, false];
      }
    }

    // Resolve default params
    const resolvedParams: Record<string, unknown> = {};
    if (params) {
      Object.assign(resolvedParams, params);
    }
    for (const pDef of workflowDef.params) {
      if (!(pDef.name in resolvedParams) && pDef.default !== undefined) {
        resolvedParams[pDef.name] = pDef.default;
      }
    }

    // Create new run
    const firstStep =
      workflowDef.steps.length > 0 ? workflowDef.steps[0].id : null;
    let run = await this.store.createRun({
      workflowId: workflowDef.id,
      workflowVersion: workflowDef.version,
      params: Object.keys(resolvedParams).length > 0 ? resolvedParams : undefined,
      projectId: options?.projectId,
      parentRunId: options?.parentRunId,
      parentStepId: options?.parentStepId,
    });

    // Set the first step
    run = await this.store.updateStep(run.id, firstStep ?? null);

    return [run, true];
  }

  // -----------------------------------------------------------------------
  // advance
  // -----------------------------------------------------------------------

  async advance(
    run: WorkflowRunState,
    workflowDef: WorkflowDefinition,
    options?: AdvanceOptions,
  ): Promise<AdvanceResult> {
    const stepOutput = options?.stepOutput ?? null;
    const notes = options?.notes ?? null;
    const resourceResolver = options?.resourceResolver;

    if (
      run.status !== WorkflowRunStatus.ACTIVE &&
      run.status !== WorkflowRunStatus.PAUSED
    ) {
      return { run, completed: true };
    }

    const currentStep = this.getStep(workflowDef, run.currentStep ?? "");
    if (!currentStep) {
      // No current step -- workflow is complete
      run = await this.store.updateStep(run.id, null, {
        status: WorkflowRunStatus.COMPLETED,
      });
      return { run, completed: true };
    }

    // Dialog steps have their own advancement logic
    if (currentStep.type === "dialog") {
      return this.dialogHandler.advanceDialog(
        run,
        workflowDef,
        currentStep,
        stepOutput,
        notes,
        (step, output, wfDef) => this.resolveNext(step, output, wfDef),
        (wfDef, stepId) => this.getStep(wfDef, stepId ?? ""),
        (output, captures) => DefaultWorkflowEngine.parseStepOutput(output, captures),
        resourceResolver,
      );
    }

    // Process captures
    const stateUpdates: Record<string, unknown> = {};
    if (stepOutput && currentStep.capture.length > 0) {
      const outputCaptures = currentStep.capture.filter(
        (c) => c.source === "output",
      );
      Object.assign(
        stateUpdates,
        DefaultWorkflowEngine.parseStepOutput(stepOutput, outputCaptures),
      );
    }

    if (notes) {
      stateUpdates["_notes"] = notes;
    }

    // Determine next step
    const nextStepId = this.resolveNext(currentStep, stepOutput, workflowDef);

    // Handle workflow step type (sub-workflow)
    if (currentStep.type === "workflow" && currentStep.workflow_ref) {
      run = await this.store.updateStep(run.id, run.currentStep ?? null, {
        stateData: stateUpdates,
        status: WorkflowRunStatus.PAUSED,
      });
      return {
        run,
        completed: false,
        subWorkflowRef: currentStep.workflow_ref,
        subWorkflowParams: currentStep.params_mapping,
      };
    }

    if (nextStepId) {
      // Check depends_on before moving to the next step
      const nextStep = this.getStep(workflowDef, nextStepId);
      if (nextStep) {
        const [depsOk, missing] = this.validateDependsOn(run, nextStep);
        if (!depsOk) {
          // Dependencies not met — save current state but don't move
          run = await this.store.updateStep(run.id, run.currentStep ?? null, {
            stateData: stateUpdates,
          });
          return { run, completed: false, blocked: true, blockedBy: missing };
        }
      }

      // Move to next step
      run = await this.store.updateStep(run.id, nextStepId, {
        stateData: stateUpdates,
      });
      if (nextStep) {
        const prompt = this.assemblePrompt(
          workflowDef,
          run,
          nextStep,
          resourceResolver,
        );
        const result: AdvanceResult = { run, prompt, completed: false };
        // Propagate delegate info for execute steps
        if (nextStep.type === "execute" && "delegate" in nextStep && nextStep.delegate) {
          result.delegate = nextStep.delegate;
          result.delegateInstructions = ("instructions" in nextStep ? nextStep.instructions : null) ?? null;
          result.delegateTools = nextStep.tools.length > 0 ? nextStep.tools : null;
        }
        return result;
      }
    }

    // No next step -- complete
    run = await this.store.updateStep(run.id, run.currentStep ?? null, {
      stateData: stateUpdates,
      status: WorkflowRunStatus.COMPLETED,
    });
    return { run, completed: true };
  }

  // -----------------------------------------------------------------------
  // assemblePrompt
  // -----------------------------------------------------------------------

  assemblePrompt(
    workflowDef: WorkflowDefinition,
    run: WorkflowRunState,
    step?: AnyStepDefinition,
    resourceResolver?: ResourceResolver,
  ): string {
    if (!step) {
      step = this.getStep(workflowDef, run.currentStep ?? "");
    }
    if (!step) {
      return "";
    }
    return this.promptBuilder.assemblePrompt(
      workflowDef,
      run,
      step,
      resourceResolver,
    );
  }

  // -----------------------------------------------------------------------
  // getStep
  // -----------------------------------------------------------------------

  getStep(
    workflowDef: WorkflowDefinition,
    stepId: string,
  ): AnyStepDefinition | undefined {
    if (!stepId) {
      return undefined;
    }
    return workflowDef.steps.find((s) => s.id === stepId);
  }

  // -----------------------------------------------------------------------
  // checkLifecycle
  // -----------------------------------------------------------------------

  checkLifecycle(
    run: WorkflowRunState,
    lifecycle?: LifecycleDefinition | null,
  ): WorkflowRunStatus | null {
    return LifecycleChecker.checkLifecycle(run, lifecycle);
  }

  // -----------------------------------------------------------------------
  // validateDependsOn
  // -----------------------------------------------------------------------

  validateDependsOn(
    run: WorkflowRunState,
    step: AnyStepDefinition,
  ): [boolean, string[]] {
    if (step.depends_on.length === 0) {
      return [true, []];
    }

    const state = run.stateData;
    const missing: string[] = [];
    for (const dep of step.depends_on) {
      for (const field of dep.fields) {
        if (!(field in state)) {
          missing.push(field);
        }
      }
    }
    return [missing.length === 0, missing];
  }

  // -----------------------------------------------------------------------
  // handleOnError
  // -----------------------------------------------------------------------

  handleOnError(
    _run: WorkflowRunState,
    step: AnyStepDefinition,
    error: string,
  ): ErrorAction {
    if (!step.on_error) {
      return { action: "abort", message: error };
    }

    const onErr = step.on_error;
    if (onErr.retry && onErr.retry > 0) {
      return { action: "retry", message: onErr.message ?? error };
    } else if (onErr.fallback) {
      return {
        action: "fallback",
        fallbackStep: onErr.fallback,
        message: onErr.message ?? error,
      };
    }
    return { action: "abort", message: onErr.message ?? error };
  }

  // -----------------------------------------------------------------------
  // resolveTemplates (public convenience)
  // -----------------------------------------------------------------------

  resolveTemplates(text: string, context: Record<string, unknown>): string {
    return PromptBuilder.resolveTemplates(text, context);
  }

  // -----------------------------------------------------------------------
  // Private: parseStepOutput
  // -----------------------------------------------------------------------

  /**
   * Parse step_output and assign per-key values.
   *
   * - If output is a JSON dict -> extract value per capture.key
   * - If output is plain string and only 1 capture -> assign directly
   * - If output is plain string and N captures -> assign whole string to each
   */
  static parseStepOutput(
    stepOutput: string | null | undefined,
    captures: CaptureDefinition[],
  ): Record<string, unknown> {
    if (!stepOutput || captures.length === 0) {
      return {};
    }

    // Try JSON parse
    try {
      const parsed: unknown = JSON.parse(stepOutput);
      if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) {
        const parsedDict = parsed as Record<string, unknown>;
        const result: Record<string, unknown> = {};
        for (const cap of captures) {
          if (cap.key in parsedDict) {
            result[cap.key] = parsedDict[cap.key];
          } else {
            // Key not in JSON -> assign whole output as fallback
            result[cap.key] = stepOutput;
          }
        }
        return result;
      }
    } catch {
      // Not valid JSON -- fall through to plain string handling
    }

    // Plain string
    const result: Record<string, unknown> = {};
    for (const cap of captures) {
      result[cap.key] = stepOutput;
    }
    return result;
  }

  // -----------------------------------------------------------------------
  // Private: resolveNext
  // -----------------------------------------------------------------------

  /**
   * Resolve the next step ID.
   *
   * Priority: choice option.next > step.next > sequential.
   */
  private resolveNext(
    currentStep: AnyStepDefinition,
    output: string | null | undefined,
    workflowDef: WorkflowDefinition,
  ): string | null {
    // For choice steps, check if output matches an option with a specific next
    if (currentStep.type === "choice" && output && currentStep.options.length > 0) {
      for (const opt of currentStep.options) {
        if (opt.key === output && opt.next) {
          return opt.next;
        }
      }
    }

    // Explicit next
    if (currentStep.next) {
      return currentStep.next;
    }

    // Sequential -- find next step in definition
    const stepIds = workflowDef.steps.map((s) => s.id);
    const idx = stepIds.indexOf(currentStep.id);
    if (idx !== -1 && idx + 1 < stepIds.length) {
      return stepIds[idx + 1];
    }

    return null;
  }
}
