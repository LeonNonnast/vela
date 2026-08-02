/**
 * Prompt assembly and template resolution for workflow steps.
 *
 * Pure logic -- no store dependency. Handles template resolution,
 * progress indicators, resource assembly, and CTAs.
 */

import type { WorkflowRunState } from "./types.js";
import type { ResourceDefinition } from "../schemas/resource.js";
import type {
  AnyStepDefinition,
  WorkflowDefinition,
} from "../schemas/workflow.js";
import { getLocale, type Locale } from "../locale/locale.js";

/** Resolves a resource ref ID to its definition. */
export type ResourceResolver = (refId: string) => ResourceDefinition | undefined;

/**
 * Resolves a run's `projectId` to arbitrary project data, exposed in
 * templates as `{{project.x}}`. The SDK ships no implementation — the
 * embedding app supplies one (e.g. backed by its own project store).
 */
export type ProjectDataResolver = (projectId: string) => Record<string, unknown> | undefined;

// ---------------------------------------------------------------------------
// PromptBuilder
// ---------------------------------------------------------------------------

export class PromptBuilder {
  /**
   * Build nested context dict for template resolution.
   *
   * Supports: {{params.X}}, {{steps.step_id.capture_key}}, {{state.key}}
   */
  static buildTemplateContext(
    workflowDef: WorkflowDefinition,
    run: WorkflowRunState,
    projectDataResolver?: ProjectDataResolver,
  ): Record<string, unknown> {
    const state = run.stateData;
    const params = run.params;

    // Build steps context: map step_id -> {capture_key: value}
    const stepsContext: Record<string, Record<string, unknown>> = {};
    for (const stepDef of workflowDef.steps) {
      const stepData: Record<string, unknown> = {};
      for (const cap of stepDef.capture) {
        if (cap.key in state) {
          stepData[cap.key] = state[cap.key];
        }
      }
      if (Object.keys(stepData).length > 0) {
        stepsContext[stepDef.id] = stepData;
      }
    }

    // {{resolved.x}} — the subset of params flagged `resolve: true` in the
    // workflow definition. Same values as `params.x`, just also reachable
    // under this name.
    const resolved: Record<string, unknown> = {};
    for (const pDef of workflowDef.params) {
      if (pDef.resolve && pDef.name in params) {
        resolved[pDef.name] = params[pDef.name];
      }
    }

    // {{project.x}} — populated only if the caller supplied a resolver.
    const project = run.projectId ? (projectDataResolver?.(run.projectId) ?? {}) : {};

    // {{fetch.x}} — results of the current step's `fetch` definitions,
    // recomputed each time a step is entered (see `resolveFetchesForStep`).
    const fetch = (state["_fetch"] as Record<string, unknown> | undefined) ?? {};

    return {
      params,
      steps: stepsContext,
      state,
      resolved,
      project,
      fetch,
    };
  }

  /** Resolve {{variable}} templates in text. */
  static resolveTemplates(text: string, context: Record<string, unknown>): string {
    return text.replace(/\{\{(.+?)\}\}/g, (_match, rawKey: string) => {
      const key = rawKey.trim();
      const keyParts = key.split(".");
      let value: unknown = context;
      for (const part of keyParts) {
        if (value !== null && typeof value === "object" && !Array.isArray(value)) {
          value = (value as Record<string, unknown>)[part];
          if (value === undefined) {
            return `{{${key}}}`;
          }
        } else {
          return `{{${key}}}`;
        }
      }
      return String(value);
    });
  }

  /**
   * Assemble resource sections for the prompt.
   *
   * Merges workflow-level and step-level resources (step wins on same ref).
   * Resources < 500 chars are inlined; others are listed as URI references.
   */
  static assembleResources(
    workflowDef: WorkflowDefinition,
    step: AnyStepDefinition,
    resourceResolver: ResourceResolver,
    forceInline = false,
    locale?: Locale,
  ): string[] {
    const loc = locale ?? getLocale();

    // Merge: workflow-level first, step-level overrides
    const merged = new Map<string, { ref: string; inline?: boolean | null }>();
    for (const ref of workflowDef.resources) {
      merged.set(ref.ref, ref);
    }
    for (const ref of step.resources) {
      merged.set(ref.ref, ref);
    }

    if (merged.size === 0) {
      return [];
    }

    const inlineParts: string[] = [];
    const referenceParts: string[] = [];

    for (const [, resRef] of merged) {
      const resource = resourceResolver(resRef.ref);
      if (!resource) {
        continue;
      }

      // Determine inline vs reference
      // Delegate steps always inline — the subagent is a separate session
      // and cannot load resources on demand.
      let shouldInline = forceInline || resRef.inline;
      if (shouldInline == null) {
        shouldInline = resource.content.length < 500;
      }

      if (shouldInline) {
        inlineParts.push(`### ${resource.name}`);
        inlineParts.push(resource.content);
        inlineParts.push("");
      } else {
        const uri =
          resource.uri_pattern ?? `vela://${resource.type}/${resource.id}`;
        const desc = resource.description ? ` — ${resource.description}` : "";
        referenceParts.push(`- \`${uri}\`${desc}`);
      }
    }

    const parts: string[] = [];
    if (inlineParts.length > 0) {
      parts.push(...inlineParts);
    }
    if (referenceParts.length > 0) {
      parts.push(loc.engineResourcesHeading);
      parts.push(...referenceParts);
      parts.push(loc.engineResourcesLoadHint);
    }

    return parts;
  }

  /**
   * Assemble the prompt for a step.
   *
   * Includes progress overview, depends_on context, resources, step prompt,
   * capture info, and CTA.
   */
  assemblePrompt(
    workflowDef: WorkflowDefinition,
    run: WorkflowRunState,
    step: AnyStepDefinition,
    resourceResolver?: ResourceResolver,
    locale?: Locale,
    projectDataResolver?: ProjectDataResolver,
  ): string {
    const loc = locale ?? getLocale();
    const state = run.stateData;
    const context = PromptBuilder.buildTemplateContext(workflowDef, run, projectDataResolver);

    const parts: string[] = [];

    // Header with step name
    const stepName = step.name ?? step.id;
    parts.push(`## ${workflowDef.name} — ${stepName}`);
    parts.push("");

    // Progress overview
    parts.push(loc.engineProgressHeading);
    for (const s of workflowDef.steps) {
      const sName = s.name ?? s.id;
      if (s.id === step.id) {
        parts.push(loc.engineProgressCurrentLine.replace("{step_name}", sName));
      } else if (s.capture.some((cap) => cap.key in state)) {
        parts.push(`- ~~${sName}~~ ✓`);
      } else {
        parts.push(`- ${sName}`);
      }
    }
    parts.push("");

    // depends_on context
    if (step.depends_on.length > 0) {
      parts.push(loc.engineDependsOnHeading);
      for (const dep of step.depends_on) {
        for (const field of dep.fields) {
          const value = state[field] ?? loc.engineNotCaptured;
          parts.push(`- **${field}**: ${value}`);
        }
      }
      parts.push("");
    }

    // Resources — force inline for delegate steps (subagent has no resource access)
    const isDelegate =
      step.type === "execute" && "delegate" in step && !!step.delegate;
    if (resourceResolver) {
      const resourceParts = PromptBuilder.assembleResources(
        workflowDef,
        step,
        resourceResolver,
        isDelegate,
        loc,
      );
      if (resourceParts.length > 0) {
        parts.push(...resourceParts);
        parts.push("");
      }
    }

    // Workflow-level tool requirements
    if (workflowDef.tools.length > 0) {
      parts.push(loc.engineToolsRequiredHeading);
      for (const t of workflowDef.tools) {
        const serverHint = t.server ? ` (${t.server})` : "";
        const descHint = t.description ? ` — ${t.description}` : "";
        const reqHint = t.required ? loc.engineRequiredTag : loc.engineOptionalTag;
        parts.push(`- **${t.name}**${serverHint}${descHint} ${reqHint}`);
      }
      parts.push("");
    }

    // Step-level tool hints
    if (step.tools.length > 0) {
      const toolList = step.tools.map((t) => `\`${t}\``).join(", ");
      parts.push(loc.engineStepToolsHeading);
      parts.push(loc.engineUseTheseTools.replace("{tools}", toolList));
      parts.push("");
    }

    // Step prompt with template resolution
    const prompt = PromptBuilder.resolveTemplates(step.prompt, context);
    parts.push(prompt);

    // Choice options
    if (step.type === "choice" && step.options.length > 0) {
      parts.push("");
      parts.push(loc.engineOptionsHeading);
      for (let i = 0; i < step.options.length; i++) {
        const opt = step.options[i];
        const desc = opt.description ? ` — ${opt.description}` : "";
        parts.push(`${i + 1}. **${opt.label}**${desc}`);
      }
    }

    // Capture info
    if (step.capture.length > 0) {
      parts.push("");
      const keys = step.capture.map((c) => c.key);
      parts.push(loc.engineCapturesHint.replace("{keys}", keys.join(", ")));
    }

    // CTA
    parts.push("");
    switch (step.type) {
      case "confirm":
        parts.push(loc.engineCtaConfirm);
        break;
      case "choice":
        parts.push(loc.engineCtaChoice);
        break;
      case "freeform":
        parts.push(loc.engineCtaFreeform);
        break;
      case "execute":
        if ("delegate" in step && step.delegate) {
          parts.push(loc.engineCtaDelegate.replace("{delegate}", step.delegate));
        } else {
          parts.push(loc.engineCtaExecute);
        }
        break;
      case "dialog":
        if (state["_dialog_phase"]) {
          parts.push(loc.engineCtaDialogContinue);
        } else {
          parts.push(loc.engineCtaDialogStart);
        }
        break;
      default:
        break;
    }

    return parts.join("\n");
  }
}
