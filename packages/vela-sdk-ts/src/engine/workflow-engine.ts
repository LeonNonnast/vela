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
import { PromptBuilder, type ProjectDataResolver, type ResourceResolver } from "./prompt-builder.js";
import {
  type AdvanceResult,
  type ErrorAction,
  type WorkflowRunState,
  WorkflowRunStatus,
} from "./types.js";
import type {
  AnyStepDefinition,
  CaptureDefinition,
  DelegateStepDefinition,
  LifecycleDefinition,
  McpCallStepDefinition,
  WorkflowDefinition,
} from "../schemas/workflow.js";
import type { WorkflowStore } from "../storage/store.js";
import { resolveDelegate } from "../delegate/registry.js";
import type { DelegateContext } from "../delegate/types.js";
import { resolveSource } from "../sources/registry.js";
import type { SourceContext } from "../sources/types.js";
import type { Locale } from "../locale/locale.js";

// ---------------------------------------------------------------------------
// Options types
// ---------------------------------------------------------------------------

export interface StartOptions {
  params?: Record<string, unknown>;
  /**
   * Values for params flagged `resolve: true`, already resolved by the
   * calling app from its own context (analogous to how `identity` params
   * are supplied). Exposed in templates as `{{resolved.x}}`. Wins over
   * `params`/defaults for resolve-flagged param names.
   */
  resolvedParams?: Record<string, unknown>;
  projectId?: string | null;
  parentRunId?: string | null;
  parentStepId?: string | null;
}

export interface AdvanceOptions {
  stepOutput?: string | null;
  notes?: string | null;
  resourceResolver?: ResourceResolver;
  /** Resolves `run.projectId` to data exposed as `{{project.x}}`. */
  projectDataResolver?: ProjectDataResolver;
  /**
   * Cancellation signal propagated to delegate-step and mcp_call/fetch
   * handlers. Non-in-engine step types ignore this — they are advanced
   * synchronously.
   */
  signal?: AbortSignal;
  /**
   * Optional structured-log sink forwarded to delegate-step and
   * mcp_call/fetch handlers. Defaults to a no-op when omitted.
   */
  log?: (msg: string, meta?: unknown) => void;
  /** Locale for prompt assembly. Defaults to English when omitted. */
  locale?: Locale;
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
    locale?: Locale,
    projectDataResolver?: ProjectDataResolver,
  ): string;

  /**
   * Explicitly pause an active run. Throws if the run isn't `ACTIVE`, or if
   * `workflowDef.lifecycle.allow_pause` is `false`. Resuming is just calling
   * `advance()` again — it already accepts runs in `PAUSED` status.
   */
  pauseRun(
    run: WorkflowRunState,
    workflowDef: WorkflowDefinition,
  ): Promise<WorkflowRunState>;

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
    const finalParams: Record<string, unknown> = {};
    if (params) {
      Object.assign(finalParams, params);
    }
    for (const pDef of workflowDef.params) {
      if (!(pDef.name in finalParams) && pDef.default !== undefined) {
        finalParams[pDef.name] = pDef.default;
      }
    }
    // {{resolved.x}} — resolve-flagged params: values the caller already
    // resolved from its own context win over `params`/defaults.
    const resolvedParams = options?.resolvedParams;
    if (resolvedParams) {
      for (const pDef of workflowDef.params) {
        if (pDef.resolve && pDef.name in resolvedParams) {
          finalParams[pDef.name] = resolvedParams[pDef.name];
        }
      }
    }

    // Create new run
    const firstStep =
      workflowDef.steps.length > 0 ? workflowDef.steps[0].id : null;
    let run = await this.store.createRun({
      workflowId: workflowDef.id,
      workflowVersion: workflowDef.version,
      params: Object.keys(finalParams).length > 0 ? finalParams : undefined,
      projectId: options?.projectId,
      parentRunId: options?.parentRunId,
      parentStepId: options?.parentStepId,
    });

    // Set the first step
    run = await this.store.updateStep(run.id, firstStep ?? null);

    // Run the first step's `fetch` definitions (if any) now — it's the only
    // place this can happen, since `assemblePrompt` for the first step is
    // synchronous and called separately by the caller after this returns.
    const firstStepDef = firstStep ? this.getStep(workflowDef, firstStep) : undefined;
    if (firstStepDef && firstStepDef.fetch.length > 0) {
      const onErr = firstStepDef.on_error;
      const maxAttempts = onErr && onErr.retry > 0 ? onErr.retry + 1 : 1;
      let fetchData: Record<string, unknown> | undefined;
      let lastErrorMessage: string | undefined;

      for (let attempt = 0; attempt < maxAttempts; attempt++) {
        try {
          fetchData = await this.executeFetches(firstStepDef, run, workflowDef, undefined, undefined);
          break;
        } catch (err) {
          lastErrorMessage = err instanceof Error ? err.message : String(err);
        }
      }

      if (fetchData !== undefined) {
        run = await this.store.updateStep(run.id, run.currentStep ?? null, {
          stateData: { _fetch: fetchData },
        });
      } else {
        const outcome = await this.transitionOnFailure(
          run,
          firstStepDef,
          workflowDef,
          lastErrorMessage ?? "fetch failed",
        );
        run = outcome.run;
      }
    }

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
    let stepOutput = options?.stepOutput ?? null;
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

    // Delegate steps run their registered handler in-place. The handler's
    // returned value is JSON-stringified and treated as `stepOutput` so the
    // normal capture pipeline kicks in below. Any caller-provided
    // `options.stepOutput` is ignored for delegate steps — the handler is
    // the source of truth.
    //
    // Unlike other step types, delegate handlers execute inside the engine
    // itself (no agent round-trip), so `on_error` can be applied
    // automatically here instead of leaving it to the caller.
    if (currentStep.type === "delegate") {
      if (!resolveDelegate(currentStep.delegate)) {
        throw new Error(
          `No handler registered for delegate '${currentStep.delegate}' (step '${currentStep.id}')`,
        );
      }

      const onErr = currentStep.on_error;
      const maxAttempts = onErr && onErr.retry > 0 ? onErr.retry + 1 : 1;
      let delegateResult: unknown;
      let handlerSucceeded = false;
      let lastErrorMessage: string | undefined;

      for (let attempt = 0; attempt < maxAttempts; attempt++) {
        try {
          delegateResult = await this.executeDelegateStep(
            currentStep,
            run,
            workflowDef,
            options?.signal,
            options?.log,
          );
          handlerSucceeded = true;
          break;
        } catch (err) {
          lastErrorMessage = err instanceof Error ? err.message : String(err);
        }
      }

      if (!handlerSucceeded) {
        return this.applyEngineStepFailure(
          run,
          currentStep,
          workflowDef,
          lastErrorMessage ?? "delegate handler failed",
          resourceResolver,
          options?.locale,
          options?.projectDataResolver,
        );
      }

      stepOutput =
        typeof delegateResult === "string"
          ? delegateResult
          : JSON.stringify(delegateResult ?? null);
    }

    // mcp_call steps make a single server-side tool call via the source
    // registry (see ../sources/registry.ts) and auto-advance — no agent
    // round-trip, same in-engine execution + automatic on_error as
    // `delegate` above.
    if (currentStep.type === "mcp_call") {
      let mcpResult: unknown;
      let handlerSucceeded = false;
      let lastErrorMessage: string | undefined;

      const onErr = currentStep.on_error;
      const maxAttempts = onErr && onErr.retry > 0 ? onErr.retry + 1 : 1;

      for (let attempt = 0; attempt < maxAttempts; attempt++) {
        try {
          mcpResult = await this.executeMcpCallStep(
            currentStep,
            run,
            workflowDef,
            options?.signal,
            options?.log,
          );
          handlerSucceeded = true;
          break;
        } catch (err) {
          lastErrorMessage = err instanceof Error ? err.message : String(err);
        }
      }

      if (!handlerSucceeded) {
        return this.applyEngineStepFailure(
          run,
          currentStep,
          workflowDef,
          lastErrorMessage ?? "mcp_call failed",
          resourceResolver,
          options?.locale,
          options?.projectDataResolver,
        );
      }

      stepOutput =
        typeof mcpResult === "string" ? mcpResult : JSON.stringify(mcpResult ?? null);
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
        options?.locale,
        async (step, r, wfDef) => {
          const outcome = await this.resolveFetchesForStep(step, r, wfDef, options);
          if (!outcome.ok) {
            const result = await this.applyEngineStepFailure(
              r,
              step,
              wfDef,
              outcome.errorMessage,
              resourceResolver,
              options?.locale,
              options?.projectDataResolver,
            );
            return { ok: false, result };
          }
          if (!outcome.fetchData) {
            return { ok: true, run: r };
          }
          const updated = await this.store.updateStep(r.id, r.currentStep ?? null, {
            stateData: { _fetch: outcome.fetchData },
          });
          return { ok: true, run: updated };
        },
        options?.projectDataResolver,
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

      // Run this step's `fetch` definitions (if any) before landing on it,
      // so {{fetch.x}} is populated by the time its prompt is assembled.
      if (nextStep) {
        const fetchOutcome = await this.resolveFetchesForStep(
          nextStep,
          { ...run, currentStep: nextStepId, stateData: { ...run.stateData, ...stateUpdates } },
          workflowDef,
          options,
        );
        if (!fetchOutcome.ok) {
          run = await this.store.updateStep(run.id, nextStepId, { stateData: stateUpdates });
          return this.applyEngineStepFailure(
            run,
            nextStep,
            workflowDef,
            fetchOutcome.errorMessage,
            resourceResolver,
            options?.locale,
            options?.projectDataResolver,
          );
        }
        if (fetchOutcome.fetchData) {
          stateUpdates["_fetch"] = fetchOutcome.fetchData;
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
          options?.locale,
          options?.projectDataResolver,
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
    locale?: Locale,
    projectDataResolver?: ProjectDataResolver,
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
      locale,
      projectDataResolver,
    );
  }

  // -----------------------------------------------------------------------
  // pauseRun
  // -----------------------------------------------------------------------

  async pauseRun(
    run: WorkflowRunState,
    workflowDef: WorkflowDefinition,
  ): Promise<WorkflowRunState> {
    if (run.status !== WorkflowRunStatus.ACTIVE) {
      throw new Error(`cannot pause run '${run.id}' — status is '${run.status}', not 'active'`);
    }
    if (workflowDef.lifecycle && workflowDef.lifecycle.allow_pause === false) {
      throw new Error(`workflow '${workflowDef.id}' has lifecycle.allow_pause: false`);
    }
    return this.store.updateStep(run.id, run.currentStep ?? null, {
      status: WorkflowRunStatus.PAUSED,
    });
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
  // Private: executeDelegateStep
  // -----------------------------------------------------------------------

  /**
   * Run the registered handler for a `delegate` step.
   *
   * Builds a `DelegateContext` from the current run + workflow definition,
   * runs the handler, and returns its result. The caller normalises the
   * result to `stepOutput` (string) for downstream capture parsing.
   *
   * @throws if no handler is registered for `step.delegate`.
   */
  private async executeDelegateStep(
    step: DelegateStepDefinition,
    run: WorkflowRunState,
    workflowDef: WorkflowDefinition,
    signal: AbortSignal | undefined,
    log: ((msg: string, meta?: unknown) => void) | undefined,
  ): Promise<unknown> {
    const handler = resolveDelegate(step.delegate);
    if (!handler) {
      throw new Error(
        `No handler registered for delegate '${step.delegate}' (step '${step.id}')`,
      );
    }

    // Snapshot the template context so resolveVars can chase params, state,
    // and prior step captures without re-reading the store.
    const templateCtx = PromptBuilder.buildTemplateContext(workflowDef, run);

    const captureSink: Record<string, unknown> = {};
    const ctx: DelegateContext = {
      resolveVars: (v) => DefaultWorkflowEngine.resolveVarsDeep(v, templateCtx),
      setCapture: (key, value) => {
        captureSink[key] = value;
      },
      signal,
      log: log ?? ((_msg, _meta) => {}),
    };

    const result = await handler(
      { id: step.id, delegate: step.delegate, task: step.task ?? null },
      ctx,
    );

    // If the handler used `ctx.setCapture` AND returned an object, merge —
    // explicit captures win. If it returned a non-object, wrap as
    // `{ result: ... }` so captures can still target keys.
    if (Object.keys(captureSink).length > 0) {
      if (result && typeof result === "object" && !Array.isArray(result)) {
        return { ...(result as Record<string, unknown>), ...captureSink };
      }
      return { result, ...captureSink };
    }
    return result;
  }

  /**
   * Deep-walk `value` and resolve `{{...}}` templates in every string. Used
   * by `DelegateContext.resolveVars` so handlers can pass arbitrarily
   * nested `task` payloads through without manual interpolation.
   */
  static resolveVarsDeep(value: unknown, context: Record<string, unknown>): unknown {
    if (typeof value === "string") {
      return PromptBuilder.resolveTemplates(value, context);
    }
    if (Array.isArray(value)) {
      return value.map((v) => DefaultWorkflowEngine.resolveVarsDeep(v, context));
    }
    if (value !== null && typeof value === "object") {
      const out: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
        out[k] = DefaultWorkflowEngine.resolveVarsDeep(v, context);
      }
      return out;
    }
    return value;
  }

  // -----------------------------------------------------------------------
  // Private: executeMcpCallStep
  // -----------------------------------------------------------------------

  /**
   * Run the registered source handler for an `mcp_call` step.
   *
   * @throws if `mcp_source`/`mcp_tool` are missing, or no handler is
   * registered for `mcp_source`.
   */
  private async executeMcpCallStep(
    step: McpCallStepDefinition,
    run: WorkflowRunState,
    workflowDef: WorkflowDefinition,
    signal: AbortSignal | undefined,
    log: ((msg: string, meta?: unknown) => void) | undefined,
  ): Promise<unknown> {
    if (!step.mcp_source || !step.mcp_tool) {
      throw new Error(`mcp_call step '${step.id}' is missing mcp_source/mcp_tool`);
    }
    const handler = resolveSource(step.mcp_source);
    if (!handler) {
      throw new Error(
        `No handler registered for source '${step.mcp_source}' (mcp_call step '${step.id}')`,
      );
    }

    const templateCtx = PromptBuilder.buildTemplateContext(workflowDef, run);
    const resolvedParams = DefaultWorkflowEngine.resolveVarsDeep(
      step.mcp_params,
      templateCtx,
    ) as Record<string, unknown>;
    const ctx: SourceContext = { signal, log: log ?? ((_msg, _meta) => {}) };

    return handler(step.mcp_tool, resolvedParams, ctx);
  }

  // -----------------------------------------------------------------------
  // Private: executeFetches / resolveFetchesForStep
  // -----------------------------------------------------------------------

  /**
   * Run every `fetch` definition on `step` via the source registry and
   * return the results keyed by `fetch.key`.
   *
   * @throws if a fetch's `source` has no registered handler.
   */
  private async executeFetches(
    step: AnyStepDefinition,
    run: WorkflowRunState,
    workflowDef: WorkflowDefinition,
    signal: AbortSignal | undefined,
    log: ((msg: string, meta?: unknown) => void) | undefined,
  ): Promise<Record<string, unknown>> {
    const templateCtx = PromptBuilder.buildTemplateContext(workflowDef, run);
    const ctx: SourceContext = { signal, log: log ?? ((_msg, _meta) => {}) };

    const result: Record<string, unknown> = {};
    for (const fetchDef of step.fetch) {
      const handler = resolveSource(fetchDef.source);
      if (!handler) {
        throw new Error(
          `No handler registered for source '${fetchDef.source}' (fetch key '${fetchDef.key}' on step '${step.id}')`,
        );
      }
      const resolvedParams = DefaultWorkflowEngine.resolveVarsDeep(
        fetchDef.params,
        templateCtx,
      ) as Record<string, unknown>;
      result[fetchDef.key] = await handler(fetchDef.action, resolvedParams, ctx);
    }
    return result;
  }

  /**
   * Resolve `step.fetch` (if any) for a step the engine just landed on.
   *
   * No-ops (returns `{ ok: true }` with no `fetchData`) when the step
   * declares no `fetch` entries and there's no stale `_fetch` to clear —
   * zero behavior change for workflows that don't use `fetch`. On failure,
   * applies `step.on_error` (retry/fallback/abort) the same way `delegate`
   * and `mcp_call` do.
   */
  private async resolveFetchesForStep(
    step: AnyStepDefinition,
    run: WorkflowRunState,
    workflowDef: WorkflowDefinition,
    options: AdvanceOptions | undefined,
  ): Promise<
    | { ok: true; fetchData?: Record<string, unknown> }
    | { ok: false; errorMessage: string }
  > {
    if (step.fetch.length === 0) {
      return "_fetch" in run.stateData ? { ok: true, fetchData: {} } : { ok: true };
    }

    const onErr = step.on_error;
    const maxAttempts = onErr && onErr.retry > 0 ? onErr.retry + 1 : 1;
    let fetchData: Record<string, unknown> | undefined;
    let lastErrorMessage: string | undefined;

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        fetchData = await this.executeFetches(
          step,
          run,
          workflowDef,
          options?.signal,
          options?.log,
        );
        break;
      } catch (err) {
        lastErrorMessage = err instanceof Error ? err.message : String(err);
      }
    }

    if (fetchData === undefined) {
      return { ok: false, errorMessage: lastErrorMessage ?? "fetch failed" };
    }
    return { ok: true, fetchData };
  }

  // -----------------------------------------------------------------------
  // Private: transitionOnFailure / applyEngineStepFailure
  // -----------------------------------------------------------------------

  /**
   * Apply `step.on_error` (fallback/abort) to `run` and persist the
   * resulting transition. Shared core used both by `applyEngineStepFailure`
   * (which also assembles the fallback step's prompt) and by
   * `startOrResume`'s first-step `fetch` handling (which doesn't need a
   * prompt — the caller assembles one separately after `startOrResume`
   * returns).
   */
  private async transitionOnFailure(
    run: WorkflowRunState,
    step: AnyStepDefinition,
    workflowDef: WorkflowDefinition,
    errorMessage: string,
  ): Promise<{ run: WorkflowRunState; message: string; fallbackStep?: AnyStepDefinition }> {
    const errorAction = this.handleOnError(run, step, errorMessage);
    const message = errorAction.message ?? errorMessage;

    if (errorAction.action === "fallback" && errorAction.fallbackStep) {
      const fallbackStep = this.getStep(workflowDef, errorAction.fallbackStep);
      run = await this.store.updateStep(run.id, errorAction.fallbackStep, {
        stateData: { _error: message },
      });
      return { run, message, fallbackStep };
    }

    // abort (default when no fallback is configured)
    run = await this.store.updateStep(run.id, run.currentStep ?? null, {
      status: WorkflowRunStatus.CANCELLED,
      stateData: { _error: message },
    });
    return { run, message };
  }

  /** `transitionOnFailure`, plus assembling the fallback step's prompt (or completing the run) into an `AdvanceResult`. */
  private async applyEngineStepFailure(
    run: WorkflowRunState,
    step: AnyStepDefinition,
    workflowDef: WorkflowDefinition,
    errorMessage: string,
    resourceResolver: ResourceResolver | undefined,
    locale: Locale | undefined,
    projectDataResolver: ProjectDataResolver | undefined,
  ): Promise<AdvanceResult> {
    const { run: updatedRun, message, fallbackStep } = await this.transitionOnFailure(
      run,
      step,
      workflowDef,
      errorMessage,
    );

    if (fallbackStep) {
      const prompt = this.assemblePrompt(
        workflowDef,
        updatedRun,
        fallbackStep,
        resourceResolver,
        locale,
        projectDataResolver,
      );
      return { run: updatedRun, prompt, completed: false, error: message };
    }
    return { run: updatedRun, completed: true, error: message };
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
