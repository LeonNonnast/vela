/**
 * Zod schemas for workflow definitions.
 *
 * Schema version: 0.3.0 — type-safe discriminated unions for step types.
 * Field names use snake_case to match YAML format.
 */

import { z } from "zod";
import { resourceReferenceSchema } from "./resource.js";

// ---------------------------------------------------------------------------
// StepType
// ---------------------------------------------------------------------------

export const stepTypeSchema = z.enum([
  "freeform",
  "choice",
  "confirm",
  "execute",
  "dialog",
  "workflow",
  "mcp_call",
]);

export type StepType = z.infer<typeof stepTypeSchema>;

// ---------------------------------------------------------------------------
// CaptureOption / CaptureDefinition
// ---------------------------------------------------------------------------

export const captureOptionSchema = z.object({
  key: z.string(),
  label: z.string(),
});

export type CaptureOption = z.infer<typeof captureOptionSchema>;

export const captureDefinitionSchema = z.object({
  key: z.string(),
  label: z.string().nullish(),
  type: z.string().default("string"),
  required: z.boolean().default(false),
  source: z.string().default("output"),

  // Elicitation strategy
  input: z.string().nullish(),
  options: z.array(captureOptionSchema).default([]),
  suggest: z.boolean().default(false),
  placeholder: z.string().nullish(),
  default: z.unknown().optional(),
  elicit: z.string().default("if_missing"),
});

export type CaptureDefinition = z.infer<typeof captureDefinitionSchema>;

// ---------------------------------------------------------------------------
// ChoiceOption
// ---------------------------------------------------------------------------

export const choiceOptionSchema = z.object({
  key: z.string(),
  label: z.string(),
  description: z.string().nullish(),
  next: z.string().nullish(),
});

export type ChoiceOption = z.infer<typeof choiceOptionSchema>;

// ---------------------------------------------------------------------------
// DialogPhaseDefinition
// ---------------------------------------------------------------------------

export const dialogPhaseDefinitionSchema = z.object({
  id: z.string(),
  name: z.string().nullish(),
  guideline: z.string(),
});

export type DialogPhaseDefinition = z.infer<typeof dialogPhaseDefinitionSchema>;

// ---------------------------------------------------------------------------
// DependsOnDefinition
// ---------------------------------------------------------------------------

export const dependsOnDefinitionSchema = z.object({
  step: z.string(),
  fields: z.array(z.string()),
});

export type DependsOnDefinition = z.infer<typeof dependsOnDefinitionSchema>;

// ---------------------------------------------------------------------------
// FetchDefinition
// ---------------------------------------------------------------------------

export const fetchDefinitionSchema = z.object({
  key: z.string(),
  source: z.string(),
  action: z.string(),
  params: z.record(z.unknown()).default({}),
});

export type FetchDefinition = z.infer<typeof fetchDefinitionSchema>;

// ---------------------------------------------------------------------------
// OnErrorDefinition
// ---------------------------------------------------------------------------

export const onErrorDefinitionSchema = z.object({
  retry: z.number().default(0),
  fallback: z.string().nullish(),
  abort: z.boolean().default(false),
  message: z.string().nullish(),
});

export type OnErrorDefinition = z.infer<typeof onErrorDefinitionSchema>;

// ---------------------------------------------------------------------------
// BaseStep (shared fields)
// ---------------------------------------------------------------------------

export const baseStepSchema = z.object({
  id: z.string(),
  name: z.string().nullish(),
  prompt: z.string().default(""),

  // Context dependencies
  depends_on: z.array(dependsOnDefinitionSchema).default([]),
  fetch: z.array(fetchDefinitionSchema).default([]),
  tools: z.array(z.string()).default([]),

  // Structured output
  capture: z.array(captureDefinitionSchema).default([]),

  // Navigation
  next: z.string().nullish(),
  notes: z.boolean().default(true),

  // Error handling
  on_error: onErrorDefinitionSchema.nullish(),

  // Resources
  resources: z.array(resourceReferenceSchema).default([]),
});

export type BaseStepDefinition = z.infer<typeof baseStepSchema>;

// ---------------------------------------------------------------------------
// Individual step schemas
// ---------------------------------------------------------------------------

export const freeformStepSchema = baseStepSchema.extend({
  type: z.literal("freeform"),
});

export type FreeformStepDefinition = z.infer<typeof freeformStepSchema>;

export const choiceStepSchema = baseStepSchema.extend({
  type: z.literal("choice"),
  options: z.array(choiceOptionSchema).default([]),
});

export type ChoiceStepDefinition = z.infer<typeof choiceStepSchema>;

export const confirmStepSchema = baseStepSchema.extend({
  type: z.literal("confirm"),
});

export type ConfirmStepDefinition = z.infer<typeof confirmStepSchema>;

export const executeStepSchema = baseStepSchema.extend({
  type: z.literal("execute"),
  instructions: z.string().nullish(),
  delegate: z.string().nullish(),
});

export type ExecuteStepDefinition = z.infer<typeof executeStepSchema>;

export const dialogStepSchema = baseStepSchema.extend({
  type: z.literal("dialog"),
  mode: z.string().nullish(),
  goal: z.string().nullish(),
  guidelines: z.array(z.string()).default([]),
  phases: z.array(dialogPhaseDefinitionSchema).default([]),
});

export type DialogStepDefinition = z.infer<typeof dialogStepSchema>;

export const workflowStepSchema = baseStepSchema.extend({
  type: z.literal("workflow"),
  workflow_ref: z.string().nullish(),
  params_mapping: z.record(z.string()).default({}),
});

export type WorkflowStepDefinition = z.infer<typeof workflowStepSchema>;

export const mcpCallStepSchema = baseStepSchema.extend({
  type: z.literal("mcp_call"),
  mcp_tool: z.string().nullish(),
  mcp_source: z.string().nullish(),
  mcp_params: z.record(z.unknown()).default({}),
});

export type McpCallStepDefinition = z.infer<typeof mcpCallStepSchema>;

// ---------------------------------------------------------------------------
// AnyStepDefinition — discriminated union on "type"
// ---------------------------------------------------------------------------

export const anyStepSchema = z.discriminatedUnion("type", [
  freeformStepSchema,
  choiceStepSchema,
  confirmStepSchema,
  executeStepSchema,
  dialogStepSchema,
  workflowStepSchema,
  mcpCallStepSchema,
]);

export type AnyStepDefinition = z.infer<typeof anyStepSchema>;

// ---------------------------------------------------------------------------
// ToolRequirement
// ---------------------------------------------------------------------------

export const toolRequirementSchema = z.object({
  name: z.string(),
  server: z.string().nullish(),
  description: z.string().nullish(),
  required: z.boolean().default(true),
});

export type ToolRequirement = z.infer<typeof toolRequirementSchema>;

// ---------------------------------------------------------------------------
// ParamDefinition
// ---------------------------------------------------------------------------

export const paramDefinitionSchema = z.object({
  name: z.string(),
  label: z.string().nullish(),
  description: z.string().nullish(),
  required: z.boolean().default(false),
  default: z.unknown().optional(),
  identity: z.boolean().default(false),
  application: z.boolean().default(false),
  resolve: z.boolean().default(false),
});

export type ParamDefinition = z.infer<typeof paramDefinitionSchema>;

// ---------------------------------------------------------------------------
// ContextAutoDefinition
// ---------------------------------------------------------------------------

export const contextAutoDefinitionSchema = z.object({
  auto: z.array(z.string()).default([]),
});

export type ContextAutoDefinition = z.infer<typeof contextAutoDefinitionSchema>;

// ---------------------------------------------------------------------------
// LifecycleDefinition
// ---------------------------------------------------------------------------

export const lifecycleDefinitionSchema = z.object({
  auto_archive_after: z.string().nullish(),
  auto_cancel_after: z.string().nullish(),
  allow_pause: z.boolean().default(true),
});

export type LifecycleDefinition = z.infer<typeof lifecycleDefinitionSchema>;

// ---------------------------------------------------------------------------
// WorkflowDefinition — the complete workflow definition
// ---------------------------------------------------------------------------

export const workflowDefinitionSchema = z.object({
  id: z.string(),
  version: z.string().default("1.0.0"),
  name: z.string(),
  description: z.string().default(""),
  params: z.array(paramDefinitionSchema).default([]),
  context: contextAutoDefinitionSchema.nullish(),
  lifecycle: lifecycleDefinitionSchema.nullish(),
  tools: z.array(toolRequirementSchema).default([]),
  resources: z.array(resourceReferenceSchema).default([]),
  steps: z.array(anyStepSchema).default([]),
});

export type WorkflowDefinition = z.infer<typeof workflowDefinitionSchema>;
