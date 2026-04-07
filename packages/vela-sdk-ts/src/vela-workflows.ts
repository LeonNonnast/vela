/**
 * VelaWorkflows — main entry point for MCP workflow integration.
 *
 * Registers MCP tools and prompts for workflow execution.
 * Framework-agnostic — works with any McpServerAdapter implementation.
 */

import type { AdvanceResult, WorkflowRunState } from "./engine/types.js";
import { WorkflowRunStatus } from "./engine/types.js";
import type { ResourceResolver } from "./engine/prompt-builder.js";
import {
  type IWorkflowEngine,
  DefaultWorkflowEngine,
} from "./engine/workflow-engine.js";
import type { Locale } from "./locale/locale.js";
import { getLocale } from "./locale/locale.js";
import {
  parseWorkflowYaml,
  parseAgentYaml,
  parseResourceYaml,
} from "./loader/yaml-loader.js";
import type {
  McpContext,
  McpServerAdapter,
} from "./mcp/mcp-server.js";
import { HeadlessAdapter } from "./adapters/headless.js";
import {
  autoAdvanceLoop,
  elicitStepCaptures,
  stepCapturesComplete,
} from "./mcp/auto-advance.js";
import {
  type WorkflowResolver,
  type SessionProvider,
  type ParamFilter,
  type ProjectResolver,
  type AsyncSession,
  InMemoryWorkflowResolver,
  SimpleSessionProvider,
  DefaultParamFilter,
} from "./mcp/protocols.js";
import {
  toJson,
  runToDict,
  buildResponse,
  buildStepResponse,
  buildNextAction,
  enrichSubWorkflowResponse,
  enrichToolRequirements,
} from "./mcp/response-builder.js";
import {
  elicitMissingParams,
  elicitPromptSession,
} from "./mcp/session-elicitor.js";
import type { AgentDefinition } from "./schemas/agent.js";
import type { ResourceDefinition } from "./schemas/resource.js";
import type { WorkflowDefinition } from "./schemas/workflow.js";
import { InMemoryStore } from "./storage/memory-store.js";
import type { WorkflowStore } from "./storage/store.js";

// ---------------------------------------------------------------------------
// Options
// ---------------------------------------------------------------------------

export interface VelaWorkflowsOptions {
  /** MCP server adapter. Defaults to HeadlessAdapter if not provided. */
  server?: McpServerAdapter;
  engine?: IWorkflowEngine;
  store?: WorkflowStore;
  workflows?: string[];
  agents?: string[];
  resources?: string[];
  toolPrefix?: string;
  toolNameFormat?: Record<string, string>;
  locale?: Locale;
  autoAdvance?: boolean;
  registerPrompts?: boolean;
  resourceResolver?: ResourceResolver;
  workflowResolver?: WorkflowResolver;
  sessionProvider?: SessionProvider;
  paramFilter?: ParamFilter;
  projectResolver?: ProjectResolver;
}

// ---------------------------------------------------------------------------
// VelaWorkflows
// ---------------------------------------------------------------------------

export class VelaWorkflows {
  private readonly server: McpServerAdapter;
  private readonly store: WorkflowStore;
  private readonly engine: IWorkflowEngine;
  private readonly locale: Locale;
  private readonly toolPrefix: string;
  private readonly toolNames: Record<string, string>;
  private readonly autoAdvanceEnabled: boolean;
  private readonly resourceResolver?: ResourceResolver;
  private readonly projectResolver?: ProjectResolver;
  private readonly paramFilter: ParamFilter;
  private readonly sessionProvider: SessionProvider;
  private readonly resolver: WorkflowResolver;

  private readonly workflows: Record<string, WorkflowDefinition> = {};
  private readonly agents: Record<string, AgentDefinition> = {};
  private readonly resourceDefs: Record<string, ResourceDefinition> = {};

  constructor(options: VelaWorkflowsOptions) {
    this.server = options.server ?? new HeadlessAdapter();
    this.locale = options.locale ?? getLocale();
    this.toolPrefix = options.toolPrefix ?? "workflow";
    this.autoAdvanceEnabled = options.autoAdvance ?? true;
    this.resourceResolver = options.resourceResolver;
    this.projectResolver = options.projectResolver;

    // Parse YAML strings
    if (options.workflows) {
      for (const yamlStr of options.workflows) {
        const wf = parseWorkflowYaml(yamlStr);
        const key = `${wf.id}@${wf.version}`;
        this.workflows[key] = wf;
      }
    }
    if (options.agents) {
      for (const yamlStr of options.agents) {
        const agent = parseAgentYaml(yamlStr);
        this.agents[agent.id] = agent;
      }
    }
    if (options.resources) {
      for (const yamlStr of options.resources) {
        const res = parseResourceYaml(yamlStr);
        this.resourceDefs[res.id] = res;
      }
    }

    // Storage + engine defaults
    this.store = options.store ?? new InMemoryStore();
    this.engine =
      options.engine ?? new DefaultWorkflowEngine(this.store);

    // Extension protocols
    this.resolver =
      options.workflowResolver ??
      new InMemoryWorkflowResolver(this.workflows);
    this.sessionProvider =
      options.sessionProvider ?? new SimpleSessionProvider(this.store);
    this.paramFilter =
      options.paramFilter ?? new DefaultParamFilter();

    // Tool names
    const defaultNames: Record<string, string> = {
      advance: `${this.toolPrefix}_advance`,
      status: `${this.toolPrefix}_status`,
      list: `${this.toolPrefix}_list`,
    };
    if (options.toolNameFormat) {
      Object.assign(defaultNames, options.toolNameFormat);
    }
    this.toolNames = defaultNames;

    // Register tools and prompts
    this.registerTools();
    if (options.registerPrompts !== false) {
      this.registerPrompts();
    }
  }

  // -------------------------------------------------------------------------
  // register — add a workflow definition at runtime
  // -------------------------------------------------------------------------

  register(workflow: WorkflowDefinition): void {
    const key = `${workflow.id}@${workflow.version}`;
    this.workflows[key] = workflow;
    if (this.resolver instanceof InMemoryWorkflowResolver) {
      (this.resolver as any).workflows[key] = workflow;
    }

    // Register prompt so loadPrompt() can find the new workflow
    const promptName = `${this.toolPrefix}_${workflow.id}`;
    const advanceName = this.toolNames["advance"];
    const loc = this.locale;
    this.server.addPrompt({
      name: promptName,
      description: workflow.description || `Start workflow: ${workflow.name}`,
      load: async (ctx: McpContext): Promise<string> => {
        return this.buildWorkflowPrompt(workflow, advanceName, loc, ctx);
      },
    });
  }

  // -------------------------------------------------------------------------
  // Private: getWorkflow
  // -------------------------------------------------------------------------

  private async getWorkflow(
    workflowId: string,
    version?: string | null,
  ): Promise<WorkflowDefinition | null> {
    return this.resolver.getWorkflow(workflowId, version);
  }

  // -------------------------------------------------------------------------
  // Private: registerTools
  // -------------------------------------------------------------------------

  private registerTools(): void {
    const advanceName = this.toolNames["advance"];

    // Tool 1: advance
    this.server.addTool({
      name: advanceName,
      description:
        "Start, resume, or advance a workflow. " +
        "Provide workflow_id to start/resume. Provide run_id + output to advance an active step. " +
        "IMPORTANT: After calling this tool, ALWAYS execute the `next_action` from the response IMMEDIATELY " +
        "without asking the user for permission. The engine handles all user interaction via built-in elicitation " +
        "dialogs — do NOT ask the user questions yourself. Just follow the next_action instruction.",
      parameters: {
        type: "object",
        properties: {
          workflow_id: {
            type: "string",
            description: "Workflow definition ID to start or resume",
          },
          run_id: {
            type: "string",
            description: "Existing run ID to advance",
          },
          step_id: {
            type: "string",
            description: "Current step ID for validation",
          },
          output: {
            type: "string",
            description: "Step output / user response",
          },
          params: {
            type: "string",
            description: "JSON string of workflow parameters",
          },
          project_id: {
            type: "string",
            description: "Project ID for scoping",
          },
          project_slug: {
            type: "string",
            description: "Project slug (resolved to project_id)",
          },
          notes: {
            type: "string",
            description: "Agent notes for this step",
          },
        },
      },
      execute: async (
        args: Record<string, unknown>,
        ctx: McpContext,
      ): Promise<string> => {
        return this.handleAdvance(args, ctx);
      },
    });

    // Tool 2: status
    this.server.addTool({
      name: this.toolNames["status"],
      description: "Get the status of a workflow run by run_id.",
      parameters: {
        type: "object",
        properties: {
          run_id: {
            type: "string",
            description: "The workflow run ID",
          },
        },
        required: ["run_id"],
      },
      execute: async (
        args: Record<string, unknown>,
      ): Promise<string> => {
        return this.handleStatus(args);
      },
    });

    // Tool 3: list
    this.server.addTool({
      name: this.toolNames["list"],
      description: "List available workflow definitions and active runs.",
      parameters: {
        type: "object",
        properties: {
          project_id: {
            type: "string",
            description: "Filter active runs by project ID",
          },
        },
      },
      execute: async (
        args: Record<string, unknown>,
      ): Promise<string> => {
        return this.handleList(args);
      },
    });
  }

  // -------------------------------------------------------------------------
  // Private: registerPrompts
  // -------------------------------------------------------------------------

  private registerPrompts(): void {
    const advanceName = this.toolNames["advance"];
    const loc = this.locale;

    // Workflow prompts
    for (const [, wfDef] of Object.entries(this.workflows)) {
      const promptName = `${this.toolPrefix}_${wfDef.id}`;
      const description =
        wfDef.description || `Start workflow: ${wfDef.name}`;

      // Capture in closure
      const wf = wfDef;
      this.server.addPrompt({
        name: promptName,
        description,
        load: async (ctx: McpContext): Promise<string> => {
          return this.buildWorkflowPrompt(wf, advanceName, loc, ctx);
        },
      });
    }

    // Agent prompts
    for (const [, agentDef] of Object.entries(this.agents)) {
      const promptName = `agent_${agentDef.id}`;
      const description = `Agent: ${agentDef.name}`;

      const agent = agentDef;
      this.server.addPrompt({
        name: promptName,
        description,
        load: async (): Promise<string> => {
          const parts: string[] = [];
          parts.push(`# ${agent.name}`);
          parts.push("");
          if (agent.persona) {
            parts.push(agent.persona);
            parts.push("");
          }
          if (agent.greeting) {
            parts.push(agent.greeting);
            parts.push("");
          }
          if (agent.workflows.length > 0) {
            parts.push("## Available Workflows");
            for (const wfId of agent.workflows) {
              parts.push(`- ${wfId}`);
            }
            parts.push("");
          }
          return parts.join("\n");
        },
      });
    }
  }

  // -------------------------------------------------------------------------
  // Private: handleAdvance
  // -------------------------------------------------------------------------

  private async handleAdvance(
    args: Record<string, unknown>,
    ctx: McpContext,
  ): Promise<string> {
    const session = this.sessionProvider.session();
    const store = session.store;
    const engine =
      store === this.store
        ? this.engine
        : new DefaultWorkflowEngine(store);
    const resolver = this.resourceResolver;
    const advanceName = this.toolNames["advance"];
    const locale = this.locale;
    const prefix = this.toolPrefix;

    try {
      let projectId: string | null = (args.project_id as string) ?? null;
      const projectSlug = (args.project_slug as string) ?? null;
      const runId = (args.run_id as string) ?? null;
      const workflowId = (args.workflow_id as string) ?? null;
      const stepId = (args.step_id as string) ?? null;
      const output = (args.output as string) ?? null;
      const paramsStr = (args.params as string) ?? null;
      const notes = (args.notes as string) ?? null;

      // Resolve project slug
      if (!projectId && projectSlug && this.projectResolver) {
        projectId = await this.projectResolver.resolveProjectId(
          projectSlug,
        );
      }

      // Case 1: Advance existing run
      if (runId) {
        const run = await store.getById(runId);
        if (!run) {
          return toJson({ error: "Run not found", run_id: runId });
        }

        const wfDef = await this.getWorkflow(
          run.workflowId,
          run.workflowVersion,
        );
        if (!wfDef) {
          return toJson({
            error: "Workflow definition not found",
            workflow_id: run.workflowId,
          });
        }

        // Validate step_id
        if (stepId) {
          if (!engine.getStep(wfDef, stepId)) {
            return toJson({
              error: "Unknown step",
              step_id: stepId,
              workflow_id: wfDef.id,
              valid_steps: wfDef.steps.map((s) => s.id),
            });
          }
          if (stepId !== run.currentStep) {
            return toJson({
              error: "Step mismatch",
              expected_step: run.currentStep,
              provided_step: stepId,
              run_id: runId,
            });
          }
        }

        // Elicit missing captures for current step
        let currentRun = run;
        if (currentRun.currentStep && ctx) {
          currentRun = await elicitStepCaptures(
            ctx,
            engine,
            wfDef,
            currentRun,
            store,
            locale,
          );
        }

        // Only advance if captures are complete OR agent provided output
        const stepDef = engine.getStep(
          wfDef,
          currentRun.currentStep ?? "",
        );
        const canAdvance =
          output !== null ||
          !stepDef ||
          !stepDef.capture ||
          stepCapturesComplete(stepDef, currentRun);

        if (canAdvance) {
          let result = await engine.advance(currentRun, wfDef, {
            stepOutput: output,
            notes,
            resourceResolver: resolver,
          });
          await store.commit();

          if (this.autoAdvanceEnabled && ctx) {
            result = await autoAdvanceLoop(
              ctx,
              engine,
              wfDef,
              result,
              store,
              resolver,
              locale,
            );
          }

          // Handle sub-workflow: auto-start child
          if (result.subWorkflowRef) {
            const childResp = await this.startSubWorkflow(
              result,
              engine,
              store,
              ctx,
              resolver,
              prefix,
            );
            if (childResp) return childResp;
          }

          // Handle completed child: auto-resume parent
          if (result.completed && result.run.parentRunId) {
            const parentResp = await this.resumeParent(
              result.run,
              engine,
              store,
              ctx,
              resolver,
              prefix,
            );
            if (parentResp) return parentResp;
          }

          const resp = buildResponse(
            result,
            wfDef,
            engine,
            advanceName,
            locale,
          );
          await enrichSubWorkflowResponse(
            resp,
            result,
            this.resolver,
            store,
            locale,
            advanceName,
          );
          const stepD1 = engine.getStep(wfDef, result.run.currentStep ?? "");
          enrichToolRequirements(resp, wfDef, stepD1);
          return toJson(resp);
        } else {
          await store.commit();
          const resp = buildStepResponse(
            currentRun,
            wfDef,
            engine,
            resolver,
            advanceName,
            "awaiting_input",
            locale,
          );
          const stepD2 = engine.getStep(wfDef, currentRun.currentStep ?? "");
          enrichToolRequirements(resp, wfDef, stepD2);
          return toJson(resp);
        }
      }

      // Case 2: Start or resume by workflow_id
      if (!workflowId) {
        return toJson({ error: "Provide workflow_id or run_id" });
      }

      const wfDef = await this.getWorkflow(workflowId);
      if (!wfDef) {
        return toJson({
          error: "Workflow not found",
          workflow_id: workflowId,
        });
      }

      let parsedParams: Record<string, unknown> = {};
      if (paramsStr) {
        try {
          parsedParams = JSON.parse(paramsStr);
        } catch {
          return toJson({
            error: "Invalid params JSON",
            params: paramsStr,
          });
        }
      }

      // Elicit missing required params
      const missingRequired = this.paramFilter.filterMissingParams(
        wfDef,
        parsedParams,
      );
      if (missingRequired.length > 0 && ctx) {
        const activeRuns = await store.listActive({
          workflowId: wfDef.id,
        });
        const resolved = await elicitMissingParams(
          ctx,
          wfDef,
          missingRequired,
          activeRuns,
          parsedParams,
          locale,
        );
        if (resolved === null) {
          return toJson({
            status: "cancelled",
            workflow_id: wfDef.id,
            message: locale.workflowStartCancelled,
          });
        }
        Object.assign(parsedParams, resolved);
      }

      const [startedRun, isNew] = await engine.startOrResume(wfDef, {
        params: parsedParams,
        projectId,
      });

      // Elicit missing captures on first/current step
      let currentRun = startedRun;
      if (currentRun.currentStep && ctx) {
        currentRun = await elicitStepCaptures(
          ctx,
          engine,
          wfDef,
          currentRun,
          store,
          locale,
        );
      }

      await store.commit();

      // Auto-advance loop
      const stepDef = engine.getStep(
        wfDef,
        currentRun.currentStep ?? "",
      );
      if (stepDef && stepCapturesComplete(stepDef, currentRun)) {
        let result = await engine.advance(currentRun, wfDef, {
          resourceResolver: resolver,
        });
        await store.commit();
        if (this.autoAdvanceEnabled && ctx) {
          result = await autoAdvanceLoop(
            ctx,
            engine,
            wfDef,
            result,
            store,
            resolver,
            locale,
          );
        }

        // Handle sub-workflow
        if (result.subWorkflowRef) {
          const childResp = await this.startSubWorkflow(
            result,
            engine,
            store,
            ctx,
            resolver,
            prefix,
          );
          if (childResp) return childResp;
        }

        const resp = buildResponse(
          result,
          wfDef,
          engine,
          advanceName,
          locale,
        );
        await enrichSubWorkflowResponse(
          resp,
          result,
          this.resolver,
          store,
          locale,
          advanceName,
        );
        (resp as Record<string, unknown>)["status"] = isNew
          ? "started"
          : "resumed_and_advanced";
        const stepD3 = engine.getStep(wfDef, result.run.currentStep ?? "");
        enrichToolRequirements(resp, wfDef, stepD3);
        return toJson(resp);
      } else {
        const resp = buildStepResponse(
          currentRun,
          wfDef,
          engine,
          resolver,
          advanceName,
          isNew ? "started" : "resumed",
          locale,
        );
        enrichToolRequirements(resp, wfDef, stepDef);
        return toJson(resp);
      }
    } finally {
      await session.close();
    }
  }

  // -------------------------------------------------------------------------
  // Private: handleStatus
  // -------------------------------------------------------------------------

  private async handleStatus(
    args: Record<string, unknown>,
  ): Promise<string> {
    const session = this.sessionProvider.session();
    try {
      const runId = args.run_id as string;
      if (!runId) {
        return toJson({ error: "run_id is required" });
      }
      const run = await session.store.getById(runId);
      if (!run) {
        return toJson({ error: "Run not found", run_id: runId });
      }
      return toJson(runToDict(run));
    } finally {
      await session.close();
    }
  }

  // -------------------------------------------------------------------------
  // Private: handleList
  // -------------------------------------------------------------------------

  private async handleList(
    args: Record<string, unknown>,
  ): Promise<string> {
    const projectId = (args.project_id as string) ?? undefined;
    const allWorkflows = await this.resolver.listWorkflows();
    const definitions = Object.values(allWorkflows).map((wf) => ({
      id: wf.id,
      version: wf.version,
      name: wf.name,
      description: wf.description,
      tools: wf.tools.map((t) => ({
        name: t.name,
        server: t.server ?? null,
        required: t.required,
      })),
    }));

    const session = this.sessionProvider.session();
    try {
      const activeRuns = await session.store.listActive({
        projectId,
      });
      const activeDicts = activeRuns.map((r) => runToDict(r));

      return toJson({
        definitions,
        active_runs: activeDicts,
      });
    } finally {
      await session.close();
    }
  }

  // -------------------------------------------------------------------------
  // Public: buildWorkflowPrompt
  // -------------------------------------------------------------------------

  /**
   * Build a workflow prompt with optional elicitation for session choice
   * and parameter collection.
   *
   * When called via MCP prompts/get, the McpContext enables interactive
   * elicitation. When called programmatically, provide a context with a
   * custom elicit() implementation (e.g. bridged to a UI via IPC).
   */
  async buildWorkflowPrompt(
    wf: WorkflowDefinition,
    advanceName: string,
    loc: Locale,
    ctx: McpContext,
  ): Promise<string> {
    const session = this.sessionProvider.session();
    try {
      const store = session.store;
      const engine =
        store === this.store
          ? this.engine
          : new DefaultWorkflowEngine(store);
      const resolver = this.resourceResolver;

      const parts: string[] = [`# ${wf.name}`, ""];
      if (wf.description) {
        parts.push(wf.description);
        parts.push("");
      }

      const activeRuns = await store.listActive({ workflowId: wf.id });

      let chosenRun: WorkflowRunState | null = null;
      let chosenParams: Record<string, unknown> = {};
      if (activeRuns.length > 0 || wf.params.length > 0) {
        [chosenRun, chosenParams] = await elicitPromptSession(
          ctx,
          wf,
          activeRuns,
          loc,
        );
      }

      if (chosenRun) {
        const stepPrompt = engine.assemblePrompt(
          wf,
          chosenRun,
          undefined,
          resolver,
        );
        const runParams = chosenRun.params;
        const paramLabels: Record<string, string> = {};
        for (const p of wf.params) {
          paramLabels[p.name] = p.label ?? p.name;
        }
        const stepNames: Record<string, string> = {};
        for (const s of wf.steps) {
          stepNames[s.id] = s.name ?? s.id;
        }
        const stepLabel =
          stepNames[chosenRun.currentStep ?? ""] ??
          chosenRun.currentStep ??
          "";

        parts.push(loc.promptResumedSession);
        parts.push(
          loc.promptRunId.replace("{run_id}", chosenRun.id),
        );
        parts.push(
          loc.promptCurrentStep.replace("{step_label}", stepLabel),
        );
        if (Object.keys(runParams).length > 0) {
          const paramStr = Object.entries(runParams)
            .map(
              ([k, v]) =>
                `${paramLabels[k] ?? k}: ${v}`,
            )
            .join(", ");
          parts.push(
            loc.promptParameters.replace("{param_str}", paramStr),
          );
        }
        parts.push("");
        parts.push(stepPrompt);
        parts.push("");

        const nextAction = buildNextAction(
          chosenRun,
          wf,
          engine,
          advanceName,
          loc,
        );

        const currentStepDef = engine.getStep(
          wf,
          chosenRun.currentStep ?? "",
        );
        if (currentStepDef && currentStepDef.capture) {
          const state = chosenRun.stateData;
          const captured: Record<string, unknown> = {};
          const missing: string[] = [];
          for (const c of currentStepDef.capture) {
            if (c.key in state) {
              captured[c.key] = state[c.key];
            } else {
              missing.push(c.key);
            }
          }
          if (Object.keys(captured).length > 0) {
            parts.push(loc.promptCapturedData);
            for (const [k, v] of Object.entries(captured)) {
              parts.push(`- **${k}**: ${v}`);
            }
            parts.push("");
          }
          if (missing.length > 0) {
            parts.push(
              loc.promptStillOpen.replace(
                "{keys}",
                missing.join(", "),
              ),
            );
            parts.push("");
          }
        }

        parts.push(loc.promptNextAction);
        parts.push(nextAction);
      } else {
        // New workflow — show params and steps
        if (wf.params.length > 0) {
          parts.push("## Parameters");
          for (const p of wf.params) {
            const req = p.required ? " (required)" : "";
            const def =
              p.default !== undefined && p.default !== null
                ? ` [default: ${p.default}]`
                : "";
            if (p.name in chosenParams) {
              parts.push(
                `- **${p.name}**${req}: \`${chosenParams[p.name]}\``,
              );
            } else {
              parts.push(
                `- **${p.name}**${req}${def}: ${p.description ?? ""}`,
              );
            }
          }
          parts.push("");
        }

        parts.push("## Steps");
        for (const s of wf.steps) {
          const name = s.name ?? s.id;
          parts.push(`1. **${name}** (${s.type})`);
        }
        parts.push("");

        if (Object.keys(chosenParams).length > 0) {
          const paramsJson = JSON.stringify(chosenParams);
          parts.push(loc.promptNextAction);
          parts.push(
            loc.promptCallAdvanceWithParams
              .replace("{tool_name}", advanceName)
              .replace("{wf_id}", wf.id)
              .replace("{params_json}", paramsJson),
          );
        } else {
          parts.push(loc.promptNextAction);
          parts.push(
            loc.promptCallAdvance
              .replace("{tool_name}", advanceName)
              .replace("{wf_id}", wf.id),
          );
        }
      }

      parts.push("");
      parts.push(
        loc.promptAutoMode.replace(/\{tool_name\}/g, advanceName),
      );

      return parts.join("\n");
    } finally {
      await session.close();
    }
  }

  // -------------------------------------------------------------------------
  // Private: resolveSubWorkflowParams
  // -------------------------------------------------------------------------

  private async resolveSubWorkflowParams(
    parentResult: AdvanceResult,
    childWfDef: WorkflowDefinition,
  ): Promise<Record<string, unknown>> {
    const parentRun = parentResult.run;
    const parentData: Record<string, unknown> = {
      ...parentRun.params,
      ...parentRun.stateData,
    };
    const resolved: Record<string, unknown> = {};

    // Explicit mapping: {child_param: parent_key}
    const mapping = (parentResult.subWorkflowParams ?? {}) as Record<
      string,
      string
    >;
    for (const [childKey, parentKey] of Object.entries(mapping)) {
      if (parentKey in parentData) {
        resolved[childKey] = parentData[parentKey];
      }
    }

    // Auto-match: child param names that exist in parent data
    for (const pDef of childWfDef.params) {
      if (!(pDef.name in resolved) && pDef.name in parentData) {
        resolved[pDef.name] = parentData[pDef.name];
      }
    }

    return resolved;
  }

  // -------------------------------------------------------------------------
  // Private: startSubWorkflow
  // -------------------------------------------------------------------------

  private async startSubWorkflow(
    parentResult: AdvanceResult,
    engine: IWorkflowEngine,
    store: WorkflowStore,
    ctx: McpContext,
    resolver: ResourceResolver | undefined,
    _prefix: string,
  ): Promise<string | null> {
    const locale = this.locale;
    const advanceName = this.toolNames["advance"];

    const childWfDef = await this.getWorkflow(
      parentResult.subWorkflowRef!,
    );
    if (!childWfDef) {
      return null;
    }

    // Resolve params from parent state
    const childParams = await this.resolveSubWorkflowParams(
      parentResult,
      childWfDef,
    );

    // Start child run
    let [childRun] = await engine.startOrResume(childWfDef, {
      params: childParams,
      projectId: parentResult.run.projectId,
      parentRunId: parentResult.run.id,
      parentStepId: parentResult.run.currentStep,
    });

    // Elicit captures on first step
    if (childRun.currentStep && ctx) {
      childRun = await elicitStepCaptures(
        ctx,
        engine,
        childWfDef,
        childRun,
        store,
        locale,
      );
    }

    await store.commit();

    // Auto-advance child
    const childStep = engine.getStep(
      childWfDef,
      childRun.currentStep ?? "",
    );
    if (childStep && stepCapturesComplete(childStep, childRun)) {
      let childResult = await engine.advance(childRun, childWfDef, {
        resourceResolver: resolver,
      });
      await store.commit();
      if (this.autoAdvanceEnabled && ctx) {
        childResult = await autoAdvanceLoop(
          ctx,
          engine,
          childWfDef,
          childResult,
          store,
          resolver,
          locale,
        );
      }

      // If child completed immediately, resume parent
      if (childResult.completed && childResult.run.parentRunId) {
        const parentResp = await this.resumeParent(
          childResult.run,
          engine,
          store,
          ctx,
          resolver,
          _prefix,
        );
        if (parentResp) return parentResp;
      }

      const resp = buildResponse(
        childResult,
        childWfDef,
        engine,
        advanceName,
        locale,
      );
      await enrichSubWorkflowResponse(
        resp,
        childResult,
        this.resolver,
        store,
        locale,
        advanceName,
      );
      (resp as Record<string, unknown>)["parent_run_id"] =
        parentResult.run.id;
      (resp as Record<string, unknown>)["status"] =
        "sub_workflow_started";
      return toJson(resp);
    }

    // Child needs input on first step
    const resp = buildStepResponse(
      childRun,
      childWfDef,
      engine,
      resolver,
      advanceName,
      "sub_workflow_started",
      locale,
    );
    (resp as Record<string, unknown>)["parent_run_id"] =
      parentResult.run.id;
    return toJson(resp);
  }

  // -------------------------------------------------------------------------
  // Private: resumeParent
  // -------------------------------------------------------------------------

  private async resumeParent(
    childRun: WorkflowRunState,
    engine: IWorkflowEngine,
    store: WorkflowStore,
    ctx: McpContext,
    resolver: ResourceResolver | undefined,
    prefix: string,
  ): Promise<string | null> {
    const locale = this.locale;
    const advanceName = this.toolNames["advance"];

    const parentRun = await store.getById(childRun.parentRunId!);
    if (!parentRun) return null;

    const parentWfDef = await this.getWorkflow(
      parentRun.workflowId,
      parentRun.workflowVersion,
    );
    if (!parentWfDef) return null;

    // Resume parent: advance past the workflow step
    let parentResult = await engine.advance(parentRun, parentWfDef, {
      stepOutput: "sub_workflow_completed",
      resourceResolver: resolver,
    });
    await store.commit();

    if (this.autoAdvanceEnabled && ctx) {
      parentResult = await autoAdvanceLoop(
        ctx,
        engine,
        parentWfDef,
        parentResult,
        store,
        resolver,
        locale,
      );
    }

    // Recursive: if parent also hits a sub-workflow or completes with a parent
    if (parentResult.subWorkflowRef) {
      const childResp = await this.startSubWorkflow(
        parentResult,
        engine,
        store,
        ctx,
        resolver,
        prefix,
      );
      if (childResp) return childResp;
    }

    if (parentResult.completed && parentResult.run.parentRunId) {
      return this.resumeParent(
        parentResult.run,
        engine,
        store,
        ctx,
        resolver,
        prefix,
      );
    }

    const resp = buildResponse(
      parentResult,
      parentWfDef,
      engine,
      advanceName,
      locale,
    );
    await enrichSubWorkflowResponse(
      resp,
      parentResult,
      this.resolver,
      store,
      locale,
      advanceName,
    );
    (resp as Record<string, unknown>)["resumed_from_sub_workflow"] =
      childRun.workflowId;
    return toJson(resp);
  }
}
