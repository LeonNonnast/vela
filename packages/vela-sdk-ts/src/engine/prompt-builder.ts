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

/** Resolves a resource ref ID to its definition. */
export type ResourceResolver = (refId: string) => ResourceDefinition | undefined;

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

    return {
      params,
      steps: stepsContext,
      state,
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
  ): string[] {
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
      let shouldInline = resRef.inline;
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
      parts.push("### Available Resources");
      parts.push(...referenceParts);
      parts.push(
        '*Lade mit `read_resource("URI")` oder `vela_get_resource(id="...")`.* ',
      );
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
  ): string {
    const state = run.stateData;
    const context = PromptBuilder.buildTemplateContext(workflowDef, run);

    const parts: string[] = [];

    // Header with step name
    const stepName = step.name ?? step.id;
    parts.push(`## ${workflowDef.name} — ${stepName}`);
    parts.push("");

    // Progress overview
    parts.push("### Fortschritt");
    for (const s of workflowDef.steps) {
      const sName = s.name ?? s.id;
      if (s.id === step.id) {
        parts.push(`- **→ ${sName}** ← aktuell`);
      } else if (s.capture.some((cap) => cap.key in state)) {
        parts.push(`- ~~${sName}~~ ✓`);
      } else {
        parts.push(`- ${sName}`);
      }
    }
    parts.push("");

    // depends_on context
    if (step.depends_on.length > 0) {
      parts.push("### Kontext aus vorherigen Steps:");
      for (const dep of step.depends_on) {
        for (const field of dep.fields) {
          const value = state[field] ?? "(nicht erfasst)";
          parts.push(`- **${field}**: ${value}`);
        }
      }
      parts.push("");
    }

    // Resources
    if (resourceResolver) {
      const resourceParts = PromptBuilder.assembleResources(
        workflowDef,
        step,
        resourceResolver,
      );
      if (resourceParts.length > 0) {
        parts.push(...resourceParts);
        parts.push("");
      }
    }

    // Workflow-level tool requirements
    if (workflowDef.tools.length > 0) {
      parts.push("### Benötigte externe Tools");
      for (const t of workflowDef.tools) {
        const serverHint = t.server ? ` (${t.server})` : "";
        const descHint = t.description ? ` — ${t.description}` : "";
        const reqHint = t.required ? "[erforderlich]" : "[optional]";
        parts.push(`- **${t.name}**${serverHint}${descHint} ${reqHint}`);
      }
      parts.push("");
    }

    // Step-level tool hints
    if (step.tools.length > 0) {
      const toolList = step.tools.map((t) => `\`${t}\``).join(", ");
      parts.push("### Tools für diesen Step");
      parts.push(`Nutze folgende Tools: ${toolList}`);
      parts.push("");
    }

    // Step prompt with template resolution
    const prompt = PromptBuilder.resolveTemplates(step.prompt, context);
    parts.push(prompt);

    // Choice options
    if (step.type === "choice" && step.options.length > 0) {
      parts.push("");
      parts.push("### Optionen:");
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
      parts.push(`*Dieser Step erfasst: ${keys.join(", ")}*`);
    }

    // CTA
    parts.push("");
    switch (step.type) {
      case "confirm":
        parts.push("**Bitte bestaetigen oder ablehnen.**");
        break;
      case "choice":
        parts.push("**Bitte eine Option wählen.**");
        break;
      case "freeform":
        parts.push("**Bitte Eingabe machen.**");
        break;
      case "execute":
        if ("delegate" in step && step.delegate) {
          parts.push(`**Delegation an: ${step.delegate}**`);
        } else {
          parts.push("**Ausführen, dann Abschluss bestaetigen.**");
        }
        break;
      case "dialog":
        if (state["_dialog_phase"]) {
          parts.push("**Dialog fortsetzen — aktuelle Phase bearbeiten.**");
        } else {
          parts.push("**Dialog starten — advance aufrufen.**");
        }
        break;
      default:
        break;
    }

    return parts.join("\n");
  }
}
