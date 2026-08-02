// ---------------------------------------------------------------------------
// Engine
// ---------------------------------------------------------------------------
export type {
  WorkflowRunState,
  AdvanceResult,
  ErrorAction,
} from "./engine/types.js";
export { WorkflowRunStatus } from "./engine/types.js";
export type { IWorkflowEngine, StartOptions, AdvanceOptions } from "./engine/workflow-engine.js";
export { DefaultWorkflowEngine } from "./engine/workflow-engine.js";
export { PromptBuilder } from "./engine/prompt-builder.js";
export type { ResourceResolver, ProjectDataResolver } from "./engine/prompt-builder.js";
export { DialogModeRegistry } from "./engine/dialog-modes.js";

// ---------------------------------------------------------------------------
// Schemas
// ---------------------------------------------------------------------------
export {
  workflowDefinitionSchema,
  anyStepSchema,
  stepTypeSchema,
  paramDefinitionSchema,
  captureDefinitionSchema,
  choiceOptionSchema,
  baseStepSchema,
  lifecycleDefinitionSchema,
  toolRequirementSchema,
} from "./schemas/workflow.js";
export type {
  WorkflowDefinition,
  AnyStepDefinition,
  ParamDefinition,
  CaptureDefinition,
  ChoiceOption,
  StepType,
  LifecycleDefinition,
  BaseStepDefinition,
  ToolRequirement,
} from "./schemas/workflow.js";

export { agentDefinitionSchema } from "./schemas/agent.js";
export type { AgentDefinition } from "./schemas/agent.js";

export { resourceDefinitionSchema, resourceReferenceSchema } from "./schemas/resource.js";
export type { ResourceDefinition, ResourceReference } from "./schemas/resource.js";

// ---------------------------------------------------------------------------
// Delegate (Anhang F)
// ---------------------------------------------------------------------------
export {
  registerDelegate,
  resolveDelegate,
  clearDelegates,
} from "./delegate/registry.js";
export type { DelegateContext, DelegateHandler } from "./delegate/types.js";
export { makeDelegateStep } from "./delegate/step.js";
export { delegateStepSchema } from "./schemas/workflow.js";
export type { DelegateStepDefinition } from "./schemas/workflow.js";

// ---------------------------------------------------------------------------
// Sources (mcp_call step execution + fetch step field)
// ---------------------------------------------------------------------------
export {
  registerSource,
  resolveSource,
  clearSources,
} from "./sources/registry.js";
export type { SourceContext, SourceHandler } from "./sources/types.js";
export type { McpCallStepDefinition, FetchDefinition } from "./schemas/workflow.js";

// ---------------------------------------------------------------------------
// Storage
// ---------------------------------------------------------------------------
export type { WorkflowStore, CreateRunOptions, UpdateStepOptions, ListActiveOptions } from "./storage/store.js";
export { InMemoryStore } from "./storage/memory-store.js";
export { LocalStorageStore } from "./storage/local-store.js";
export type { KVStorage } from "./storage/local-store.js";

// ---------------------------------------------------------------------------
// MCP
// ---------------------------------------------------------------------------
export type {
  McpServerAdapter,
  McpToolDefinition,
  McpPromptDefinition,
  McpContext,
  ElicitResult,
} from "./mcp/mcp-server.js";
export { HeadlessAdapter } from "./adapters/headless.js";
export { AzureAgentsAdapter, createVelaAzureToolset } from "./adapters/azure-agents.js";
export type { AzureFunctionToolDefinition, VelaAzureToolsetResult } from "./adapters/azure-agents.js";

export type {
  WorkflowResolver,
  SessionProvider,
  AsyncSession,
  ParamFilter,
  ProjectResolver,
} from "./mcp/protocols.js";
export {
  InMemoryWorkflowResolver,
  SimpleSessionProvider,
  DefaultParamFilter,
} from "./mcp/protocols.js";

export { ElicitationService } from "./mcp/elicitation.js";
export { autoAdvanceLoop, elicitStepCaptures, stepCapturesComplete } from "./mcp/auto-advance.js";
export {
  toJson,
  runToDict,
  buildResponse,
  buildStepResponse,
  buildNextAction,
  buildRunOptions,
  enrichSubWorkflowResponse,
  enrichToolRequirements,
} from "./mcp/response-builder.js";
export {
  elicitMissingParams,
  elicitRequiredParams,
  elicitSessionChoice,
  elicitPromptSession,
} from "./mcp/session-elicitor.js";

// ---------------------------------------------------------------------------
// Locale
// ---------------------------------------------------------------------------
export type { Locale } from "./locale/locale.js";
export { getLocale, enLocale, deLocale } from "./locale/locale.js";

// ---------------------------------------------------------------------------
// Loader
// ---------------------------------------------------------------------------
export {
  parseWorkflowYaml,
  parseAgentYaml,
  parseResourceYaml,
  parseWorkflowFilename,
} from "./loader/yaml-loader.js";

// ---------------------------------------------------------------------------
// VelaWorkflows (main entry point)
// ---------------------------------------------------------------------------
export { VelaWorkflows } from "./vela-workflows.js";
export type { VelaWorkflowsOptions } from "./vela-workflows.js";
